"""Local Zotero library helpers (best-effort, optional dependency).

The scenario generator follows a local-first reference policy: peer-reviewed
references are mined from the user's Zotero library before any web search.
This module reads the Zotero SQLite database (``zotero.sqlite``) to enrich
the curated reference registry with exact bibliographic metadata (authors,
journal, DOI, year) and to resolve the absolute path of locally-stored PDF
attachments.

None of the core generator logic depends on Zotero being present: every
enrichment call is guarded and degrades gracefully.
"""

from __future__ import annotations

import os
import sqlite3

ZOTERO_ITEM_QUERY = """
SELECT
    i.itemID,
    (SELECT group_concat(c.lastName || ', ' || c.firstName, ', '
                         ORDER BY ic.orderIndex)
     FROM itemCreators ic
     JOIN creators c ON c.creatorID = ic.creatorID
     WHERE ic.itemID = i.itemID) AS authors,
    (SELECT dv.value FROM itemData id
     JOIN itemDataValues dv ON dv.valueID = id.valueID
     WHERE id.itemID = i.itemID
       AND id.fieldID = (SELECT fieldID FROM fields WHERE fieldName='title')) AS title,
    (SELECT dv.value FROM itemData id
     JOIN itemDataValues dv ON dv.valueID = id.valueID
     WHERE id.itemID = i.itemID
       AND id.fieldID = (SELECT fieldID FROM fields WHERE fieldName='publicationTitle')) AS journal,
    (SELECT dv.value FROM itemData id
     JOIN itemDataValues dv ON dv.valueID = id.valueID
     WHERE id.itemID = i.itemID
       AND id.fieldID = (SELECT fieldID FROM fields WHERE fieldName='DOI')) AS doi,
    (SELECT substr(dv.value, 1, 4) FROM itemData id
     JOIN itemDataValues dv ON dv.valueID = id.valueID
     WHERE id.itemID = i.itemID
       AND id.fieldID = (SELECT fieldID FROM fields WHERE fieldName='date')) AS year,
    (SELECT ia.path FROM itemAttachments ia
     WHERE ia.parentItemID = i.itemID AND ia.contentType = 'application/pdf'
     ORDER BY ia.itemID LIMIT 1) AS pdf_path
FROM items i
WHERE i.itemID IN (%s)
  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
"""


def find_zotero_db() -> str | None:
    """Locate a Zotero SQLite database from the usual locations."""
    candidates = [
        os.environ.get("ZOTERO_DB"),
        os.path.expanduser("~/Zotero/zotero.sqlite"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def load_zotero_metadata(db_path: str, item_ids: list[int]) -> dict[int, dict]:
    """Read bibliographic metadata for Zotero item ids.

    Returns ``{item_id: {authors, title, journal, doi, year, pdf_path, pdf_abs}}``.
    """
    item_ids = sorted({int(i) for i in item_ids})
    out: dict[int, dict] = {}
    if not item_ids:
        return out
    placeholders = ",".join("?" * len(item_ids))
    query = ZOTERO_ITEM_QUERY % placeholders
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = con.execute(query, item_ids).fetchall()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return out

    storage_root = os.path.join(os.path.dirname(os.path.abspath(db_path)), "storage")
    for item_id, authors, title, journal, doi, year, pdf_path in rows:
        info = {
            "authors": authors,
            "title": title,
            "journal": journal,
            "doi": doi,
            "year": int(year) if year and year.isdigit() else None,
            "pdf_path": pdf_path,
            "pdf_abs": None,
        }
        if pdf_path:
            if pdf_path.startswith("storage:"):
                rel = pdf_path[len("storage:"):]
                abs_candidate = os.path.join(storage_root, rel)
            else:
                abs_candidate = pdf_path
            if os.path.isfile(abs_candidate):
                info["pdf_abs"] = abs_candidate
        out[int(item_id)] = info
    return out


def enrich_references(conn, zotero_db_path: str) -> int:
    """Update the ``references`` table from a local Zotero database.

    Fills any missing bibliographic fields (authors, year, journal, DOI) with
    the exact local library record and resolves the absolute PDF path when
    the attachment file exists on disk.  Returns the number of rows updated.
    """
    rows = conn.execute(
        "SELECT ref_id, zotero_item_id FROM citations "
        "WHERE zotero_item_id IS NOT NULL"
    ).fetchall()
    if not rows:
        return 0

    item_ids = [int(r[1]) for r in rows]
    meta = load_zotero_metadata(zotero_db_path, item_ids)

    updated = 0
    for ref_id, item_id in rows:
        info = meta.get(int(item_id))
        if not info:
            continue
        fields: dict[str, object] = {}
        if info.get("authors"):
            fields["authors"] = info["authors"]
        if info.get("year"):
            fields["year"] = info["year"]
        if info.get("journal"):
            fields["journal"] = info["journal"]
        if info.get("doi") and not fields.get("doi"):
            fields["doi"] = info["doi"]
        if info.get("pdf_abs"):
            fields["local_pdf_path"] = info["pdf_abs"]
        elif info.get("pdf_path"):
            fields["local_pdf_path"] = info["pdf_path"]
        if not fields:
            continue
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE citations SET {set_clause} WHERE ref_id = ?",
            [*fields.values(), ref_id],
        )
        updated += 1
    return updated
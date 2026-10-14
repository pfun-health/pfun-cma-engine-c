import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

type DemoData = {
  title: string;
  summary: string;
  meals: number[];
  meal_widths: number[];
  activity_pulses: number[][];
  activity_enabled: boolean;
  activity_params: Record<string, number>;
  columns: Record<string, number[]>;
  g: number[][];
};

type Options = {
  python: string;
  scenario: string;
  pts: number;
  save?: string;
};

function parseArgs(args: string[]): Options {
  const options: Options = {
    python: "python3",
    scenario: "baseline",
    pts: 97,
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: demo.ts [--python FILE] [--scenario SLUG] [--pts N] [--save FILE]",
      );
      process.exit(0);
    }

    const value = args[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${arg}`);
    }
    if (arg === "--python") options.python = value;
    else if (arg === "--scenario") options.scenario = value;
    else if (arg === "--pts") {
      options.pts = Number(value);
      if (!Number.isInteger(options.pts) || options.pts < 2) {
        throw new Error("--pts must be an integer greater than or equal to 2");
      }
    } else if (arg === "--save") options.save = value;
    else throw new Error(`Unknown argument: ${arg}`);
    index += 1;
  }

  return options;
}

function number(value: number): string {
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude < 1e-4 || magnitude >= 1e6) return value.toExponential(4);
  return Number(value.toPrecision(6)).toString();
}

function chart(
  title: string,
  time: number[],
  series: number[][],
  markers: string[] = ["*"],
): string {
  const values = series.flat();
  let min = Math.min(...values);
  let max = Math.max(...values);
  const span = max - min || 1;
  const width = 60;
  const height = 12;
  const grid = Array.from({ length: height }, () => Array(width).fill(" "));
  const tMin = time[0];
  const tMax = time[time.length - 1];
  const tSpan = tMax - tMin || 1;

  series.forEach((line, lineIndex) => {
    line.forEach((value, pointIndex) => {
      const column = Math.round(((time[pointIndex] - tMin) / tSpan) * (width - 1));
      const row = Math.round((1 - (value - min) / span) * (height - 1));
      grid[row][column] = markers[lineIndex % markers.length];
    });
  });

  const lines = [
    `${title}  (t: ${number(tMin)} .. ${number(tMax)}, value: ${number(min)} .. ${number(max)})`,
  ];
  for (let row = 0; row < height; row += 1) {
    const value = max - (row / (height - 1)) * span;
    lines.push(`${number(value).padStart(8)} |${grid[row].join("")}|`);
  }
  lines.push(`${"".padStart(8)} +${"-".repeat(width)}+`);
  return `\`\`\`text\n${lines.join("\n")}\n\`\`\``;
}

function render(data: DemoData): string {
  const names = Object.keys(data.columns);
  const time = data.columns.t;
  const table = [
    `| ${names.join(" | ")} |`,
    `| ${names.map(() => "---:").join(" | ")} |`,
    ...time.map((_, row) =>
      `| ${names.map((name) => number(data.columns[name][row])).join(" | ")} |`,
    ),
  ];
  const activity = data.activity_enabled
    ? `enabled; pulses: ${JSON.stringify(data.activity_pulses)}`
    : "disabled";

  return [
    `# TypeScript demo: ${data.title}`,
    "",
    data.summary,
    "",
    "## Scenario inputs",
    "",
    `- meals (h): ${JSON.stringify(data.meals)}`,
    `- meal widths (h): ${JSON.stringify(data.meal_widths)}`,
    `- activity: ${activity}`,
    `- activity parameters: ${Object.entries(data.activity_params)
      .map(([key, value]) => `${key}=${number(value)}`)
      .join(", ")}`,
    "",
    "## Tabular output",
    "",
    ...table,
    "",
    "## ASCII charts",
    "",
    chart("G vs t", time, [data.columns.G]),
    "",
    chart("g vs t (per-meal rows)", time, data.g, ["#", "*", "+"]),
    "",
  ].join("\n");
}

function main(): void {
  const options = parseArgs(process.argv.slice(2));
  const result = spawnSync(
    options.python,
    ["demos/python/demo.py", "--json", "--scenario", options.scenario, "--pts", String(options.pts)],
    { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 },
  );
  if (result.error) throw result.error;
  if (result.status !== 0) {
    process.stderr.write(result.stderr);
    process.exit(result.status ?? 1);
  }

  const output = render(JSON.parse(result.stdout) as DemoData);
  process.stdout.write(output);
  if (options.save) {
    const path = resolve(options.save);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, output, "utf8");
  }
}

main();

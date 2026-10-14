import { Record, Scenario } from "./pfun_types.ts";

const repoRoot = getRepoRoot();

function getRepoRoot(relpath: string = "../.."): string {
    return resolve(dirname(fileURLToPath(import.meta.url)), relpath);
}

function loadScenarios(): Record<string, Scenario> {
    return JSON.parse(
        readFileSync(resolve(repoRoot, "demos/scenarios.json"), "utf8"),
    ) as Record<string, Scenario>;
}

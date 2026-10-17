import {
  runCmaEngine,
  MAX_POINTS,
  type ActivityParams,
  type ModelParams,
} from "../../pfun_cma_engine/ts/engine.ts";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function getRepoRoot(relpath: string = "../.."): string {
    return resolve(dirname(fileURLToPath(import.meta.url)), relpath);
}

const repoRoot = getRepoRoot();

function loadScenarios(root_path: string = repoRoot): Record<string, Scenario> {
    return JSON.parse(
        readFileSync(resolve(root_path, "demos/scenarios.json"), "utf8"),
    ) as Record<string, Scenario>;
}

const scenarios = loadScenarios();

function number(value: number): string {
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude < 1e-4 || magnitude >= 1e6) return value.toExponential(4);
  return Number(value.toPrecision(6)).toString();
}

type Scenario = {
  slug: string;
  title: string;
  summary: string;
  meals: number[];
  mealWidths: number[];
  pulses: [number, number, number][];
  activityParams: Record<string, number>;
  modelParams: Record<string, number>;
};

type Options = {
  scenario: string;
  pts: number;
  save?: string;
};


function parseArgs(args: string[]): Options {
  const options: Options = { scenario: "baseline", pts: 97 };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") {
      console.log("Usage: demo.ts [--scenario SLUG] [--pts N (2-768)] [--save FILE]");
      process.exit(0);
    }

    const value = args[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${arg}`);
    }
    if (arg === "--scenario") options.scenario = value;
    else if (arg === "--pts") {
      options.pts = Number(value);
      if (
        !Number.isInteger(options.pts) ||
        options.pts < 2 ||
        options.pts > MAX_POINTS
      ) {
        throw new Error("--pts must be an integer between 2 and 768");
      }
    } else if (arg === "--save") options.save = value;
    else throw new Error(`Unknown argument: ${arg}`);
    index += 1;
  }

  return options;
}

function chart(
  title: string,
  time: number[],
  series: number[][],
  markers: string[] = ["*"],
): string {
  let min = Infinity;
  let max = -Infinity;
  for (const line of series) {
    for (const value of line) {
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
  }
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

function render(
  scenario: Scenario,
  columns: Record<string, number[]>,
  mealComponents: number[][],
): string {
  const names = Object.keys(columns);
  const time = columns.t;
  const table = [
    `| ${names.join(" | ")} |`,
    `| ${names.map(() => "---:").join(" | ")} |`,
    ...time.map((_, row) =>
      `| ${names.map((name) => number(columns[name][row])).join(" | ")} |`,
    ),
  ];
  const activity =
    scenario.pulses.length === 0
      ? "disabled"
      : `enabled; pulses: ${JSON.stringify(scenario.pulses)}`;

  return [
    `# TypeScript demo: ${scenario.title}`,
    "",
    scenario.summary,
    "",
    "## Scenario inputs",
    "",
    `- meals (h): ${JSON.stringify(scenario.meals)}`,
    `- meal widths (h): ${JSON.stringify(scenario.mealWidths)}`,
    `- activity: ${activity}`,
    `- activity parameters: ${Object.entries(scenario.activityParams)
      .map(([key, value]) => `${key}=${number(value)}`)
      .join(", ")}`,
    "",
    "## Tabular output",
    "",
    ...table,
    "",
    "## ASCII charts",
    "",
    chart("G vs t", time, [columns.G]),
    "",
    chart("g vs t (per-meal rows)", time, mealComponents, ["#", "*", "+"]),
    "",
  ].join("\n");
}

function main(): void {
  const options = parseArgs(process.argv.slice(2));
  const scenario = scenarios[options.scenario];
  if (!scenario) {
    throw new Error(
      `Unknown scenario "${options.scenario}". Choose from: ${Object.keys(scenarios).join(", ")}`,
    );
  }

  const pointCount = options.pts;
  const meals = Float64Array.from(scenario.meals);
  const mealWidths = Float64Array.from(scenario.mealWidths);
  const time = Float64Array.from(
    { length: pointCount },
    (_, index) => (24 * index) / (pointCount - 1),
  );
  const activity =
    scenario.pulses.length === 0
      ? null
      : Float64Array.from(time, (t) =>
          Math.min(
            1,
            Math.max(
              0,
              scenario.pulses.reduce(
                (sum, [center, width, amplitude]) =>
                  sum + amplitude * Math.exp(-(((t - center) / width) ** 2)),
                0,
              ),
            ),
          ),
        );
  const result = runCmaEngine({
    time,
    modelParams: scenario.modelParams as ModelParams,
    taug:
      scenario.mealWidths.reduce((sum, width) => sum + width, 0) /
      scenario.mealWidths.length,
    mealWidths,
    meals,
    activity,
    activityParams: scenario.activityParams as ActivityParams,
  });

  const columns: Record<string, number[]> = {
    G: Array.from(result.G),
    I_E: Array.from(result.I_E),
    I_E_eff: Array.from(result.I_E_eff),
    L: Array.from(result.L),
    m: Array.from(result.m),
    c: Array.from(result.c),
    c_mod: Array.from(result.c_mod),
    A: Array.from(result.A),
    s_A: Array.from(result.s_A),
    a: Array.from(result.a),
    I_S: Array.from(result.I_S),
  };
  columns.t = Array.from(time);
  const mealComponents = Array.from({ length: meals.length }, (_, mealIndex) =>
    Array.from(
      result.g.subarray(mealIndex * pointCount, (mealIndex + 1) * pointCount),
    ),
  );
  const output = render(scenario, columns, mealComponents);
  process.stdout.write(output);
  if (options.save) {
    const path = resolve(options.save);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, output, "utf8");
  }
}

main();

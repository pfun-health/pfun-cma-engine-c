import koffi from "koffi";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

type Scenario = {
  title: string;
  summary: string;
  meals: number[];
  mealWidths: number[];
  pulses: [number, number, number][];
  activityParams: Record<string, number>;
};

type Options = {
  scenario: string;
  pts: number;
  save?: string;
};

const scenarios: Record<string, Scenario> = {
  baseline: {
    title: "Baseline circadian + meals",
    summary:
      "Reference day with breakfast, lunch, and dinner and no scheduled activity.",
    meals: [7, 11, 17.5],
    mealWidths: [1, 1, 1],
    pulses: [],
    activityParams: {
      k_A: 5,
      A_thresh: 0.3,
      gamma_A: 0.15,
      kappa_A: 0.5,
      beta_A: 0.2,
      eta_A: 0.4,
      tau_A: 2,
    },
  },
  "morning-run": {
    title: "Morning run",
    summary:
      "Moderate aerobic run before breakfast with residual insulin sensitization through the morning.",
    meals: [8, 12.5, 18.5],
    mealWidths: [0.9, 1, 1.1],
    pulses: [[6.75, 0.55, 0.55]],
    activityParams: {
      k_A: 5,
      A_thresh: 0.3,
      gamma_A: 0.18,
      kappa_A: 0.5,
      beta_A: 0.15,
      eta_A: 0.55,
      tau_A: 3,
    },
  },
  "evening-party": {
    title: "Evening meal + party",
    summary:
      "Later dinner followed by an immediate short walk and a longer block of light-to-moderate dancing.",
    meals: [7.5, 12.5, 19],
    mealWidths: [0.9, 1, 1.4],
    pulses: [
      [19.35, 0.2, 0.22],
      [21.1, 0.9, 0.34],
    ],
    activityParams: {
      k_A: 5,
      A_thresh: 0.3,
      gamma_A: 0.12,
      kappa_A: 0.5,
      beta_A: 0.08,
      eta_A: 0.3,
      tau_A: 2,
    },
  },
};

function parseArgs(args: string[]): Options {
  const options: Options = { scenario: "baseline", pts: 97 };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") {
      console.log("Usage: demo.ts [--scenario SLUG] [--pts N] [--save FILE]");
      process.exit(0);
    }

    const value = args[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${arg}`);
    }
    if (arg === "--scenario") options.scenario = value;
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
  const min = Math.min(...values);
  const max = Math.max(...values);
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

  const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
  const libraryPath =
    process.env.PFUN_CMA_ENGINE_LIB ??
    resolve(repoRoot, "pfun_cma_engine/libpfun_cma_engine.so");
  const library = koffi.load(libraryPath);
  const runCmaModel = library.func(
    "void run_cma_model(const double *t, int N, double d, double taup, double taug_val, const double *taug_vec, double B, double Cm, double toff, const double *tM, int n_meals, int *seed, double eps, const double *A_raw, double k_A, double A_thresh, double gamma_A, double kappa_A, double beta_A, double eta_A, double tau_A, double *out_L, double *out_m, double *out_c, double *out_c_mod, double *out_A, double *out_a, double *out_I_S, double *out_I_E, double *out_I_E_eff, double *out_s_A, double *out_G, double *out_g)",
  );

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
  const outputs = Array.from({ length: 11 }, () => new Float64Array(pointCount));
  outputs.push(new Float64Array(pointCount * meals.length));

  runCmaModel(
    time,
    pointCount,
    1,
    1.2,
    scenario.mealWidths.reduce((sum, width) => sum + width, 0) /
      scenario.mealWidths.length,
    mealWidths,
    0.05,
    0,
    0,
    meals,
    meals.length,
    null,
    1e-18,
    activity,
    scenario.activityParams.k_A,
    scenario.activityParams.A_thresh,
    scenario.activityParams.gamma_A,
    scenario.activityParams.kappa_A,
    scenario.activityParams.beta_A,
    scenario.activityParams.eta_A,
    scenario.activityParams.tau_A,
    ...outputs,
  );

  const columns: Record<string, number[]> = {
    G: Array.from(outputs[10]),
    I_E: Array.from(outputs[7]),
    I_E_eff: Array.from(outputs[8]),
    L: Array.from(outputs[0]),
    m: Array.from(outputs[1]),
    c: Array.from(outputs[2]),
    c_mod: Array.from(outputs[3]),
    A: Array.from(outputs[4]),
    s_A: Array.from(outputs[9]),
    a: Array.from(outputs[5]),
    I_S: Array.from(outputs[6]),
  };
  columns.t = Array.from(time);
  const mealComponents = Array.from({ length: meals.length }, (_, mealIndex) =>
    Array.from(
      outputs[11].subarray(mealIndex * pointCount, (mealIndex + 1) * pointCount),
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

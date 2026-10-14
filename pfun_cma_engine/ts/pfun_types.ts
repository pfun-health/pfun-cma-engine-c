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

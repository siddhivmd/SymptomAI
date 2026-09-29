import { useColorScheme } from "react-native";

// Same palette as the web frontend (web/styles.css).
const light = {
  bg: "#f5f7fa",
  surface: "#ffffff",
  surface2: "#eef2f6",
  text: "#16202c",
  muted: "#5b6878",
  border: "#dbe2ea",
  accent: "#0f766e",
  accentContrast: "#ffffff",
  patientBubble: "#0f766e",
  patientText: "#ffffff",
  assistantBubble: "#eef2f6",
  warnBg: "#fff7e6",
  warnBorder: "#f2c46d",
  warnText: "#6b4a00",
  errorBg: "#fdecec",
  errorText: "#9b1c1c",
  ok: "#16a34a",
  pending: "#d97706",
  bad: "#dc2626",
};

export type Theme = typeof light;

const dark: Theme = {
  bg: "#0e141b",
  surface: "#151d27",
  surface2: "#1d2733",
  text: "#e6edf3",
  muted: "#93a1b1",
  border: "#283444",
  accent: "#2dd4bf",
  accentContrast: "#062925",
  patientBubble: "#115e59",
  patientText: "#ecfeff",
  assistantBubble: "#1d2733",
  warnBg: "#2a2110",
  warnBorder: "#6b5220",
  warnText: "#f5d58a",
  errorBg: "#3a1717",
  errorText: "#fca5a5",
  ok: "#16a34a",
  pending: "#d97706",
  bad: "#dc2626",
};

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}

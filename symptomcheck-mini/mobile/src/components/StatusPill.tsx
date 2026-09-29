import { StyleSheet, Text, View } from "react-native";

import { useTheme } from "../lib/theme";
import type { BackendStatus } from "./useBackendStatus";

const LABELS: Record<BackendStatus, string> = {
  connecting: "Connecting…",
  waking: "Waking up backend…",
  online: "Online",
  offline: "Backend offline",
};

export function StatusPill({ status, mockMode }: { status: BackendStatus; mockMode: boolean }) {
  const t = useTheme();
  const dot = status === "online" ? t.ok : status === "offline" ? t.bad : t.pending;
  const label = status === "online" && mockMode ? "Online · mock mode" : LABELS[status];
  return (
    <View
      style={[styles.pill, { backgroundColor: t.surface2, borderColor: t.border }]}
      accessibilityRole="text"
      accessibilityLabel={`Backend status: ${label}`}
    >
      <View style={[styles.dot, { backgroundColor: dot }]} />
      <Text style={[styles.text, { color: t.text }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
    alignSelf: "flex-start",
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { fontSize: 12 },
});

import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError, getResults } from "../../lib/api";
import { useTheme } from "../../lib/theme";
import type { ResultsResponse } from "../../lib/types";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export default function ResultsScreen() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    getResults()
      .then((results) => {
        if (!active) return;
        setData(results);
        setError(null);
      })
      .catch((err) => {
        if (active) setError(err instanceof ApiError ? err.message : "Couldn't load results.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  // Pull-to-refresh and "Try again" both come through here.
  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    setReloadKey((k) => k + 1);
  }, []);

  return (
    <ScrollView
      style={{ backgroundColor: t.bg }}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 12 }]}
      refreshControl={<RefreshControl refreshing={loading && !!data} onRefresh={load} tintColor={t.muted} />}
    >
      <Text style={[styles.title, { color: t.text }]}>Benchmark results</Text>
      <Text style={[styles.subtitle, { color: t.muted }]}>
        How often each prompting arm put the true diagnosis first (top-1) or anywhere in its list of five (top-5),
        across the synthetic test cases.
      </Text>

      {loading && !data ? <ActivityIndicator style={{ marginTop: 24 }} color={t.muted} /> : null}

      {error ? (
        <View style={[styles.card, { backgroundColor: t.errorBg, borderColor: t.errorBg }]}>
          <Text style={{ color: t.errorText }}>{error}</Text>
          <Pressable onPress={load} accessibilityRole="button" style={{ marginTop: 8 }}>
            <Text style={{ color: t.errorText, fontWeight: "700" }}>Try again</Text>
          </Pressable>
        </View>
      ) : null}

      {data?.arms.map((a) => (
        <View key={a.arm} style={[styles.card, { backgroundColor: t.surface, borderColor: t.border }]}>
          <View style={styles.cardHead}>
            <Text style={[styles.arm, { color: t.text }]}>{a.arm}</Text>
            <Text style={[styles.meta, { color: t.muted }]}>
              {a.cases} cases · {a.avg_turns.toFixed(1)} avg turns
            </Text>
          </View>
          {(
            [
              ["Top-1", a.top1],
              ["Top-5", a.top5],
            ] as const
          ).map(([label, value]) => (
            <View key={label} style={styles.metric}>
              <View style={styles.metricHead}>
                <Text style={[styles.metricLabel, { color: t.muted }]}>{label}</Text>
                <Text style={[styles.metricValue, { color: t.text }]}>{pct(value)}</Text>
              </View>
              <View style={[styles.track, { backgroundColor: t.surface2 }]}>
                <View style={[styles.fill, { width: `${value * 100}%`, backgroundColor: t.accent }]} />
              </View>
            </View>
          ))}
        </View>
      ))}

      {data ? (
        <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.border }]}>
          <Text style={[styles.arm, { color: t.text, marginBottom: 8 }]}>Per-case results</Text>
          {data.cases.map((c, i) => {
            const hit = c.position >= 1 && c.position <= 5;
            return (
              <View
                key={`${c.case_id}-${c.arm}`}
                style={[styles.row, i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderColor: t.border }]}
              >
                <Text style={[styles.cell, { color: t.text }]}>{c.case_id}</Text>
                <Text style={[styles.cell, { color: t.muted }]}>{c.arm}</Text>
                <Text style={[styles.cellRight, { color: hit ? t.ok : t.muted, fontWeight: hit ? "700" : "400" }]}>
                  {hit ? `#${c.position}` : "not in top 5"}
                </Text>
              </View>
            );
          })}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12, paddingBottom: 32 },
  title: { fontSize: 22, fontWeight: "800" },
  subtitle: { fontSize: 13, lineHeight: 18 },
  card: { borderWidth: 1, borderRadius: 12, padding: 14 },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 },
  arm: { fontSize: 16, fontWeight: "700", textTransform: "capitalize" },
  meta: { fontSize: 12 },
  metric: { marginTop: 6 },
  metricHead: { flexDirection: "row", justifyContent: "space-between" },
  metricLabel: { fontSize: 13 },
  metricValue: { fontSize: 13, fontWeight: "700", fontVariant: ["tabular-nums"] },
  track: { height: 8, borderRadius: 4, marginTop: 4, overflow: "hidden" },
  fill: { height: "100%", borderRadius: 4 },
  row: { flexDirection: "row", paddingVertical: 7 },
  cell: { flex: 1, fontSize: 13 },
  cellRight: { flex: 1, fontSize: 13, textAlign: "right" },
});

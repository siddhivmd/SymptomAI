import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { DDxResult, PlainExplanation } from "../lib/types";
import { useTheme } from "../lib/theme";

interface Props {
  ddx: DDxResult;
  plain?: PlainExplanation | null;
}

export function DdxCard({ ddx, plain }: Props) {
  const t = useTheme();
  const [showClinical, setShowClinical] = useState(false);
  const differential = ddx.differential ?? [];
  const plainItems = plain?.items ?? [];
  const summary = plain?.summary || ddx.history_summary;

  return (
    <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.accent }]}>
      <Text style={[styles.title, { color: t.text }]}>What might be going on</Text>

      {summary ? (
        <Text style={[styles.body, { color: t.text }]}>
          <Text style={styles.bold}>What you told us: </Text>
          {summary}
        </Text>
      ) : null}
      <Text style={[styles.small, { color: t.muted, marginTop: 6 }]}>
        These are possibilities to discuss with a clinician, listed from most to least likely. They are not a diagnosis.
      </Text>

      <View style={styles.list}>
        {differential.map((item, i) => {
          const clinicalName = item.diagnosis || item.condition_name || "Unnamed";
          const p = plainItems[i];
          const name = p?.plain_name || clinicalName;
          const why = p?.explanation || item.rationale;
          const showTerm = !!p?.plain_name && p.plain_name.toLowerCase() !== clinicalName.toLowerCase();
          return (
            <View key={`${clinicalName}-${i}`} style={styles.item}>
              <View style={styles.itemHead}>
                <Text style={[styles.itemName, { color: t.text }]}>
                  {i + 1}. {name}
                </Text>
                {i === 0 ? (
                  <View style={[styles.badge, { backgroundColor: t.accent }]}>
                    <Text style={[styles.badgeText, { color: t.accentContrast }]}>Most likely</Text>
                  </View>
                ) : null}
              </View>
              {showTerm ? (
                <Text style={[styles.term, { color: t.muted }]}>Medical term: {clinicalName}</Text>
              ) : null}
              {why ? <Text style={[styles.body, { color: t.text, marginTop: 2 }]}>{why}</Text> : null}
            </View>
          );
        })}
      </View>

      {plain?.next_steps ? (
        <View style={[styles.next, { backgroundColor: t.surface2, borderLeftColor: t.accent }]}>
          <Text style={[styles.bold, { color: t.text }]}>What to do next</Text>
          <Text style={[styles.body, { color: t.text, marginTop: 4 }]}>{plain.next_steps}</Text>
        </View>
      ) : null}

      {plainItems.length ? (
        <View style={{ marginTop: 12 }}>
          <Pressable
            onPress={() => setShowClinical((v) => !v)}
            accessibilityRole="button"
            accessibilityState={{ expanded: showClinical }}
            hitSlop={8}
          >
            <Text style={[styles.bold, { color: t.muted }]}>
              {showClinical ? "▾ Hide clinical details" : "▸ Show clinical details"}
            </Text>
          </Pressable>
          {showClinical ? (
            <View style={{ marginTop: 6 }}>
              {ddx.history_summary ? (
                <Text style={[styles.small, { color: t.muted }]}>{ddx.history_summary}</Text>
              ) : null}
              {differential.map((item, i) => (
                <Text key={i} style={[styles.small, { color: t.muted, marginTop: 4 }]}>
                  <Text style={styles.bold}>
                    {i + 1}. {item.diagnosis || item.condition_name}
                  </Text>
                  {item.rationale ? ` — ${item.rationale}` : ""}
                </Text>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      <View style={[styles.disclaimer, { backgroundColor: t.warnBg }]}>
        <Text style={[styles.small, { color: t.warnText }]}>
          {ddx.disclaimer || "Educational demo only. Not a medical device."}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 12, padding: 14, marginTop: 4 },
  title: { fontSize: 17, fontWeight: "700", marginBottom: 8 },
  body: { fontSize: 15, lineHeight: 21 },
  small: { fontSize: 13, lineHeight: 18 },
  bold: { fontWeight: "700" },
  list: { marginTop: 10 },
  item: { marginBottom: 14 },
  itemHead: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8 },
  itemName: { fontSize: 15, fontWeight: "700", flexShrink: 1 },
  badge: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  term: { fontSize: 12, fontStyle: "italic", marginTop: 1 },
  next: { borderLeftWidth: 3, borderRadius: 8, padding: 12 },
  disclaimer: { borderRadius: 8, padding: 10, marginTop: 12 },
});

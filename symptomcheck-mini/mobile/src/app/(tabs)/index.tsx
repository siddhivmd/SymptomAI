import Ionicons from "@expo/vector-icons/Ionicons";
import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { DdxCard } from "../../components/DdxCard";
import { StatusPill } from "../../components/StatusPill";
import { useBackendStatus } from "../../components/useBackendStatus";
import { ApiError, sendChat } from "../../lib/api";
import { useTheme } from "../../lib/theme";
import type { Arm, ArmChoice, ChatMessage, DDxResult, PlainExplanation } from "../../lib/types";

const ARMS: Arm[] = ["base", "structured", "dynamic"];
const ARM_CHOICES: { value: ArmChoice; label: string }[] = [
  { value: "random", label: "Random" },
  { value: "base", label: "Base" },
  { value: "structured", label: "Structured" },
  { value: "dynamic", label: "Dynamic" },
];
const ARM_DESCRIPTIONS: Record<Arm, string> = {
  base: "Conversational baseline with no inquiry protocol. Usually doesn't end with a diagnosis card.",
  structured: "Fixed history questions over 4–5 turns (location, onset, severity, quality…).",
  dynamic: "3–4 targeted follow-ups chosen to tell likely conditions apart.",
};

const randomArm = (): Arm => ARMS[Math.floor(Math.random() * ARMS.length)];

export default function ConsultationScreen() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const { status, mockMode, markOnline } = useBackendStatus();

  const [armChoice, setArmChoice] = useState<ArmChoice>("random");
  const [arm, setArm] = useState<Arm>(randomArm);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [ddx, setDdx] = useState<DDxResult | null>(null);
  const [plain, setPlain] = useState<PlainExplanation | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<ChatMessage>>(null);

  const done = ddx !== null;

  const reset = useCallback((choice: ArmChoice) => {
    setMessages([]);
    setDdx(null);
    setPlain(null);
    setError(null);
    setInput("");
    setArm(choice === "random" ? randomArm() : choice);
  }, []);

  const chooseArm = (choice: ArmChoice) => {
    if (choice === armChoice) return;
    const apply = () => {
      setArmChoice(choice);
      reset(choice);
    };
    if (messages.length === 0) return apply();
    Alert.alert("Start a new consultation?", "Changing the arm clears the current conversation.", [
      { text: "Cancel", style: "cancel" },
      { text: "Change arm", style: "destructive", onPress: apply },
    ]);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy || done) return;
    const history: ChatMessage[] = [...messages, { role: "patient", content: text }];
    setMessages(history);
    setInput("");
    setError(null);
    setBusy(true);
    try {
      const res = await sendChat(arm, history);
      markOnline();
      setMessages([...history, { role: "assistant", content: res.message }]);
      if (res.complete && res.ddx_result) {
        setDdx(res.ddx_result);
        setPlain(res.explanation ?? null);
      }
    } catch (err) {
      // Roll back the unanswered message so the history sent next time stays consistent.
      setMessages(messages);
      setInput(text);
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const renderMessage = ({ item, index }: { item: ChatMessage; index: number }) => {
    const isPatient = item.role === "patient";
    const isFinal = done && !isPatient && index === messages.length - 1;
    const text = isFinal ? "Thanks — I have enough information. Here is what might be going on." : item.content;
    return (
      <View style={[styles.msg, isPatient ? styles.msgPatient : styles.msgAssistant]}>
        <View
          style={[
            styles.bubble,
            isPatient
              ? { backgroundColor: t.patientBubble, borderBottomRightRadius: 4 }
              : { backgroundColor: t.assistantBubble, borderBottomLeftRadius: 4 },
          ]}
        >
          <Text style={[styles.bubbleText, { color: isPatient ? t.patientText : t.text }]} selectable>
            {text}
          </Text>
        </View>
        {!isPatient ? (
          <Text style={[styles.meta, { color: t.muted }]}>Educational demo only — not medical advice.</Text>
        ) : null}
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={[styles.flex, { backgroundColor: t.bg }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + 8, backgroundColor: t.surface, borderColor: t.border }]}>
        <View style={styles.headerRow}>
          <Text style={[styles.appTitle, { color: t.text }]}>🩺 SymptomCheck</Text>
          <StatusPill status={status} mockMode={mockMode} />
        </View>
        <Text style={[styles.disclaimer, { color: t.warnText, backgroundColor: t.warnBg, borderColor: t.warnBorder }]}>
          Educational demo, not a medical device. Always consult a licensed clinician.
        </Text>

        <View style={styles.chips} accessibilityRole="radiogroup">
          {ARM_CHOICES.map((c) => {
            const selected = c.value === armChoice;
            return (
              <Pressable
                key={c.value}
                onPress={() => chooseArm(c.value)}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                style={[
                  styles.chip,
                  { borderColor: selected ? t.accent : t.border, backgroundColor: selected ? t.accent : t.surface },
                ]}
              >
                <Text style={[styles.chipText, { color: selected ? t.accentContrast : t.text }]}>{c.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.armRow}>
          <Text style={[styles.armDesc, { color: t.muted }]} numberOfLines={2}>
            <Text style={{ color: t.text, fontWeight: "700" }}>
              {arm}
              {armChoice === "random" ? " (random)" : ""}:{" "}
            </Text>
            {ARM_DESCRIPTIONS[arm]}
          </Text>
          <Pressable
            onPress={() => reset(armChoice)}
            accessibilityRole="button"
            accessibilityLabel="Reset consultation"
            hitSlop={10}
            style={[styles.resetBtn, { borderColor: t.border, backgroundColor: t.surface2 }]}
          >
            <Ionicons name="refresh" size={18} color={t.text} />
          </Pressable>
        </View>
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(_, i) => String(i)}
        renderItem={renderMessage}
        contentContainerStyle={[styles.listContent, messages.length === 0 && styles.listEmpty]}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        keyboardShouldPersistTaps="handled"
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyTitle, { color: t.text }]}>Describe what you’re experiencing</Text>
            <Text style={[styles.emptyHint, { color: t.muted }]}>
              For example: “I have a burning chest pain after eating spicy food.”
            </Text>
          </View>
        }
        ListFooterComponent={
          <View>
            {busy ? (
              <View style={[styles.msg, styles.msgAssistant]}>
                <View style={[styles.bubble, styles.typing, { backgroundColor: t.assistantBubble }]}>
                  <ActivityIndicator size="small" color={t.muted} />
                  <Text style={{ color: t.muted, marginLeft: 8 }}>
                    {status === "online" ? "Thinking…" : "Waking up the backend…"}
                  </Text>
                </View>
              </View>
            ) : null}
            {ddx ? <DdxCard ddx={ddx} plain={plain} /> : null}
          </View>
        }
      />

      {error ? (
        <View style={[styles.error, { backgroundColor: t.errorBg }]} accessibilityRole="alert">
          <Text style={{ color: t.errorText }}>{error}</Text>
        </View>
      ) : null}

      <View style={[styles.composer, { borderColor: t.border, backgroundColor: t.surface }]}>
        <TextInput
          style={[styles.input, { color: t.text, borderColor: t.border, backgroundColor: t.bg }]}
          value={input}
          onChangeText={setInput}
          placeholder={done ? "Consultation complete — tap ↻ to start again" : "Describe your symptoms…"}
          placeholderTextColor={t.muted}
          editable={!busy && !done}
          multiline
          maxLength={2000}
          accessibilityLabel="Your message"
        />
        <Pressable
          onPress={send}
          disabled={busy || done || !input.trim()}
          accessibilityRole="button"
          accessibilityLabel="Send"
          style={({ pressed }) => [
            styles.sendBtn,
            { backgroundColor: t.accent, opacity: busy || done || !input.trim() ? 0.45 : pressed ? 0.8 : 1 },
          ]}
        >
          <Ionicons name="send" size={18} color={t.accentContrast} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: { paddingHorizontal: 16, paddingBottom: 10, borderBottomWidth: 1, gap: 8 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  appTitle: { fontSize: 20, fontWeight: "800" },
  disclaimer: { fontSize: 12, borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, overflow: "hidden" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  chipText: { fontSize: 13, fontWeight: "600" },
  armRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  armDesc: { flex: 1, fontSize: 12, lineHeight: 16 },
  resetBtn: { borderWidth: 1, borderRadius: 8, padding: 7 },
  listContent: { padding: 16, gap: 10 },
  listEmpty: { flexGrow: 1, justifyContent: "center" },
  empty: { alignItems: "center", paddingHorizontal: 24 },
  emptyTitle: { fontSize: 16, fontWeight: "700", marginBottom: 4, textAlign: "center" },
  emptyHint: { fontSize: 14, textAlign: "center" },
  msg: { maxWidth: "85%" },
  msgPatient: { alignSelf: "flex-end", alignItems: "flex-end" },
  msgAssistant: { alignSelf: "flex-start" },
  bubble: { borderRadius: 16, paddingHorizontal: 13, paddingVertical: 9 },
  bubbleText: { fontSize: 15, lineHeight: 21 },
  typing: { flexDirection: "row", alignItems: "center" },
  meta: { fontSize: 11, marginTop: 3 },
  error: { marginHorizontal: 12, marginBottom: 8, padding: 10, borderRadius: 8 },
  composer: { flexDirection: "row", alignItems: "flex-end", gap: 8, padding: 10, borderTopWidth: 1 },
  input: { flex: 1, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, fontSize: 15, maxHeight: 130 },
  sendBtn: { width: 44, height: 44, borderRadius: 10, alignItems: "center", justifyContent: "center" },
});

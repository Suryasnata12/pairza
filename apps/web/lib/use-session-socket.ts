"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useSessionSocketStore } from "@/stores/use-session-socket-store";
import type { ChatMessage } from "@/types";
import { toast } from "sonner";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
const MAX_RECONNECT_DELAY_MS = 8000;

export function useSessionSocket(sessionId: string | null) {
  const queryClient = useQueryClient();
  const { addMessage, setMessages, setPartnerOnline, setPartnerTyping, setConnectionStatus, reset } =
    useSessionSocketStore();

  const wsRef = useRef<WebSocket | null>(null);
  const retryDelayRef = useRef(500);
  const cancelledRef = useRef(false);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    cancelledRef.current = false;
    reset();

    api
      .get<ChatMessage[]>(`/sessions/${sessionId}/messages`)
      .then((history) => !cancelledRef.current && setMessages(history))
      .catch(() => {});

    function invalidateSession() {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    }

    async function connect() {
      if (cancelledRef.current) return;
      setConnectionStatus("connecting");

      let ticket: string;
      try {
        const res = await api.post<{ ticket: string }>("/auth/ws-ticket");
        ticket = res.ticket;
      } catch {
        scheduleReconnect();
        return;
      }
      if (cancelledRef.current) return;

      const ws = new WebSocket(`${WS_BASE}/api/ws/session/${sessionId}?ticket=${ticket}`);
      wsRef.current = ws;

      ws.onopen = () => {
        retryDelayRef.current = 500;
        setConnectionStatus("connected");
      };

      ws.onmessage = (event) => {
        try {
          const { type, payload } = JSON.parse(event.data);
          switch (type) {
            case "message.created":
              addMessage(payload as ChatMessage);
              break;
            case "user.online":
              setPartnerOnline(true);
              break;
            case "user.offline":
              setPartnerOnline(false);
              break;
            case "user.typing":
              setPartnerTyping(true);
              if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
              typingTimeoutRef.current = setTimeout(() => setPartnerTyping(false), 3000);
              break;
            case "evidence.added":
              invalidateSession();
              break;
            case "mystery.progress":
              invalidateSession();
              toast.success("Your stranger unlocked the next stage.");
              break;
            case "mystery.solved":
              invalidateSession();
              break;
            case "session.expiring":
              invalidateSession();
              toast.warning("This investigation expires soon.");
              break;
            case "session.expired":
              invalidateSession();
              break;
            case "answer.incorrect":
              invalidateSession();
              break;
            case "error":
              toast.error(payload?.message ?? "Something went wrong.");
              break;
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setConnectionStatus("disconnected");
        if (!cancelledRef.current) scheduleReconnect();
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    function scheduleReconnect() {
      const delay = retryDelayRef.current;
      retryDelayRef.current = Math.min(delay * 1.7, MAX_RECONNECT_DELAY_MS);
      setTimeout(() => {
        if (!cancelledRef.current) connect();
      }, delay);
    }

    connect();

    return () => {
      cancelledRef.current = true;
      wsRef.current?.close();
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  function sendMessage(content: string) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "message.send", content }));
    }
  }

  function sendTyping() {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "typing" }));
    }
  }

  return { sendMessage, sendTyping };
}

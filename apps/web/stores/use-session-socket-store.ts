import { create } from "zustand";
import type { ChatMessage } from "@/types";

interface SessionSocketState {
  messages: ChatMessage[];
  partnerOnline: boolean;
  partnerTyping: boolean;
  connectionStatus: "connecting" | "connected" | "disconnected";
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;
  setPartnerOnline: (online: boolean) => void;
  setPartnerTyping: (typing: boolean) => void;
  setConnectionStatus: (status: "connecting" | "connected" | "disconnected") => void;
  reset: () => void;
}

export const useSessionSocketStore = create<SessionSocketState>((set) => ({
  messages: [],
  partnerOnline: false,
  partnerTyping: false,
  connectionStatus: "connecting",
  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setPartnerOnline: (partnerOnline) => set({ partnerOnline }),
  setPartnerTyping: (partnerTyping) => set({ partnerTyping }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  reset: () => set({ messages: [], partnerOnline: false, partnerTyping: false, connectionStatus: "connecting" }),
}));

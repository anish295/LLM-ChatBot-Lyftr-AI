import type { ApiErrorKind, ChatMetadata } from "./api";

export interface UserItem {
  kind: "user";
  id: string;
  content: string;
  simulate?: string;
}

export interface AssistantItem {
  kind: "assistant";
  id: string;
  content: string;
  metadata: ChatMetadata;
  /** The user prompt that produced this reply (for cache-speedup insight). */
  prompt: string;
  /** live latency / cache latency for the same prompt, if known. */
  speedup?: number | null;
  simulate?: string;
}

export interface ErrorItem {
  kind: "error";
  id: string;
  errorKind: ApiErrorKind;
  message: string;
  retryText: string;
}

export type ChatItem = UserItem | AssistantItem | ErrorItem;

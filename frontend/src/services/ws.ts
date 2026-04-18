import type { WsStateSyncPayload } from "../types/game";
import { wsUrlForGame } from "./api";

export type WsStatus = "idle" | "connecting" | "online" | "offline";

type WsHandlers = {
  onMessage: (payload: WsStateSyncPayload) => void;
  onStatus: (status: WsStatus, retryCount: number) => void;
  onError: (message: string) => void;
};

export class GameWsClient {
  private gameId: string;
  private handlers: WsHandlers;
  private socket: WebSocket | null = null;
  private retryCount = 0;
  private manualClose = false;
  private reconnectTimer: number | null = null;

  constructor(gameId: string, handlers: WsHandlers) {
    this.gameId = gameId;
    this.handlers = handlers;
  }

  connect(): void {
    this.manualClose = false;
    this.connectInternal();
  }

  disconnect(): void {
    this.manualClose = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.handlers.onStatus("idle", this.retryCount);
  }

  requestSync(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(JSON.stringify({ type: "sync_request" }));
  }

  private connectInternal(): void {
    this.handlers.onStatus("connecting", this.retryCount);
    try {
      this.socket = new WebSocket(wsUrlForGame(this.gameId));
    } catch (error) {
      this.handlers.onError(String(error));
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this.retryCount = 0;
      this.handlers.onStatus("online", this.retryCount);
      this.requestSync();
    };

    this.socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as WsStateSyncPayload;
        this.handlers.onMessage(payload);
      } catch {
        this.handlers.onError("ws message json parse failed");
      }
    };

    this.socket.onclose = () => {
      this.socket = null;
      if (this.manualClose) {
        this.handlers.onStatus("idle", this.retryCount);
        return;
      }
      this.handlers.onStatus("offline", this.retryCount);
      this.scheduleReconnect();
    };

    this.socket.onerror = () => {
      this.handlers.onError("ws connection error");
    };
  }

  private scheduleReconnect(): void {
    if (this.manualClose) {
      return;
    }
    this.retryCount += 1;
    const delayMs = Math.min(12000, 700 * 2 ** Math.min(this.retryCount, 4));
    this.reconnectTimer = window.setTimeout(() => {
      this.connectInternal();
    }, delayMs);
  }
}

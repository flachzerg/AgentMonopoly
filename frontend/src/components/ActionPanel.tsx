import { useEffect, useMemo, useState, type FC } from "react";

import type { ActionOption, GameState } from "../types/game";

type Props = {
  state: GameState;
  busy: boolean;
  wsStatus: "idle" | "connecting" | "online" | "offline";
  error: string | null;
  onSubmitAction: (action: string, args: Record<string, unknown>) => Promise<void>;
  onOpenReplay: () => void;
  onReconnect: () => void;
};

const ACTION_LABELS: Record<string, string> = {
  roll_dice: "掷骰子",
  event_choice: "事件选择",
  accept_alliance: "同意联盟",
  reject_alliance: "拒绝联盟",
  buy_property: "买入地产",
  skip_buy: "跳过买入",
  pass: "跳过",
};

function buildInitialArgs(option: ActionOption | undefined): Record<string, unknown> {
  if (!option) {
    return {};
  }
  return { ...option.default_args };
}

export const ActionPanel: FC<Props> = ({
  state,
  busy,
  wsStatus,
  error,
  onSubmitAction,
  onOpenReplay,
  onReconnect,
}) => {
  const [selectedAction, setSelectedAction] = useState<string>("");
  const [args, setArgs] = useState<Record<string, unknown>>({});

  const optionMap = useMemo(
    () => new Map(state.allowed_actions.map((item) => [item.action, item])),
    [state.allowed_actions]
  );

  const selectedOption = optionMap.get(selectedAction) ?? state.allowed_actions[0];

  useEffect(() => {
    const firstAction = state.allowed_actions[0]?.action ?? "";
    setSelectedAction(firstAction);
    setArgs(buildInitialArgs(state.allowed_actions[0]));
  }, [state.allowed_actions]);

  const handleActionChange = (actionName: string): void => {
    setSelectedAction(actionName);
    setArgs(buildInitialArgs(optionMap.get(actionName)));
  };

  const handleArgChange = (key: string, value: string): void => {
    const allowed = selectedOption?.allowed_values[key];
    let parsed: unknown = value;
    if (Array.isArray(allowed) && allowed.length > 0 && typeof allowed[0] === "number") {
      const asNumber = Number(value);
      parsed = Number.isFinite(asNumber) ? asNumber : value;
    }
    setArgs((current) => ({ ...current, [key]: parsed }));
  };

  const requiredArgs = selectedOption?.required_args ?? [];
  const actionCount = state.allowed_actions.length;
  const isHumanWaiting = state.waiting_for_human;
  const isHumanRoll = state.human_wait_reason === "roll_dice";
  const isHumanDecision = state.human_wait_reason === "branch_decision";
  const hasConnectionIssue = wsStatus === "offline" || error !== null;
  const isReconnectPending = wsStatus === "connecting";
  const currentActionLabel =
    ACTION_LABELS[selectedAction] ??
    ACTION_LABELS[state.allowed_actions[0]?.action ?? ""] ??
    "等待动作下发";

  const statusBanner = useMemo(() => {
    if (hasConnectionIssue) {
      return {
        tone: "error" as const,
        text: error ? `连接异常：${error}` : "连接断开，点击主按钮重连。",
      };
    }
    if (state.status === "finished") {
      return {
        tone: "success" as const,
        text: "对局已结束，可进入复盘页查看全量过程与结论。",
      };
    }
    if (state.status === "running" && state.waiting_for_human) {
      if (state.human_wait_reason === "roll_dice") {
        return {
          tone: "info" as const,
          text: "等待真人掷骰。完成后系统会继续自动推进。",
        };
      }
      if (state.human_wait_reason === "branch_decision") {
        return {
          tone: "info" as const,
          text: "等待真人做分支选择，请确认当前动作与参数。",
        };
      }
      return {
        tone: "info" as const,
        text: "等待真人动作输入。",
      };
    }
    if (state.status === "running" && !state.waiting_for_human) {
      return {
        tone: "muted" as const,
        text: "系统正在自动推进，当前不需要手动操作。",
      };
    }
    return {
      tone: "muted" as const,
      text: "对局准备中，请等待状态刷新。",
    };
  }, [error, hasConnectionIssue, state.human_wait_reason, state.status, state.waiting_for_human]);

  const primaryAction = useMemo(() => {
    if (hasConnectionIssue) {
      return {
        label: isReconnectPending ? "重连中..." : "重试/重连",
        disabled: busy || isReconnectPending,
        onClick: onReconnect,
      };
    }
    if (state.status === "finished") {
      return {
        label: "进入复盘页",
        disabled: false,
        onClick: onOpenReplay,
      };
    }
    if (state.status === "running" && state.waiting_for_human) {
      return {
        label: `执行：${currentActionLabel}`,
        disabled: busy || !selectedAction,
        onClick: () => onSubmitAction(selectedAction, args),
      };
    }
    if (state.status === "running" && !state.waiting_for_human) {
      return {
        label: "系统推进中（禁用）",
        disabled: true,
        onClick: () => undefined,
      };
    }
    return {
      label: "等待系统启动",
      disabled: true,
      onClick: () => undefined,
    };
  }, [
    args,
    busy,
    currentActionLabel,
    hasConnectionIssue,
    isReconnectPending,
    onOpenReplay,
    onReconnect,
    onSubmitAction,
    selectedAction,
    state.status,
    state.waiting_for_human,
  ]);

  if (actionCount === 0 && state.status !== "finished" && !hasConnectionIssue) {
    return (
      <section className="panel action-panel">
        <h2>动作区</h2>
        <div className="action-meta">
          <span>当前玩家：{state.current_player_id}</span>
          <span>阶段：{state.current_phase}</span>
        </div>
        <p className="muted">
          {isHumanWaiting
            ? "等待真人操作。"
            : "当前阶段由系统自动推进中，无需手动操作。"}
        </p>
      </section>
    );
  }

  return (
    <section className="panel action-panel">
      <div className="taskbar-main">
        <div className="taskbar-status">
          <h2>任务栏</h2>
          <div className="action-meta">
            <span>当前玩家：{state.current_player_id}</span>
            <span>阶段：{state.current_phase}</span>
          </div>
          <p className="action-hint">
            {isHumanRoll ? "当前只需掷骰子，系统将自动完成后续流程。" : null}
            {isHumanDecision ? "到达分支决策点，请完成必要选择。" : null}
          </p>
        </div>
        <div className={`action-status-banner action-status-banner--${statusBanner.tone}`}>{statusBanner.text}</div>

        {state.status === "running" && state.waiting_for_human && actionCount > 1 ? (
          <label className="field action-inline-field">
            <span>动作</span>
            <select
              value={selectedAction}
              onChange={(event) => handleActionChange(event.target.value)}
              disabled={busy}
            >
              {state.allowed_actions.map((option) => (
                <option key={option.action} value={option.action}>
                  {ACTION_LABELS[option.action] ?? option.action}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {state.status === "running" && state.waiting_for_human
          ? requiredArgs.map((argKey) => {
          const allowedValues = selectedOption?.allowed_values[argKey];
          if (Array.isArray(allowedValues) && allowedValues.length > 0) {
            return (
              <label key={argKey} className="field action-inline-field">
                <span>{argKey}</span>
                <select
                  value={String(args[argKey] ?? "")}
                  onChange={(event) => handleArgChange(argKey, event.target.value)}
                  disabled={busy}
                >
                  {allowedValues.map((value) => (
                    <option key={String(value)} value={String(value)}>
                      {String(value)}
                    </option>
                  ))}
                </select>
              </label>
            );
          }

          return (
            <label key={argKey} className="field action-inline-field">
              <span>{argKey}</span>
              <input
                value={String(args[argKey] ?? "")}
                onChange={(event) => handleArgChange(argKey, event.target.value)}
                disabled={busy}
              />
            </label>
          );
            })
          : null}

        <button
          type="button"
          className="btn-primary taskbar-action-btn"
          disabled={primaryAction.disabled}
          onClick={primaryAction.onClick}
        >
          {primaryAction.label}
        </button>
      </div>
      <p className="muted">所有动作均由后端白名单与参数校验判定。</p>
    </section>
  );
};

import { useEffect, useMemo, useState, type FC } from "react";

import type { ActionOption, GameState } from "../types/game";

type Props = {
  state: GameState;
  busy: boolean;
  onSubmitAction: (action: string, args: Record<string, unknown>) => Promise<void>;
  onTriggerAgent: () => Promise<void>;
  onAutoPlayAgents: () => Promise<void>;
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
  onSubmitAction,
  onTriggerAgent,
  onAutoPlayAgents,
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

  return (
    <section className="panel">
      <h2>动作区</h2>
      <div className="action-meta">
        <span>current player: {state.current_player_id}</span>
        <span>phase: {state.current_phase}</span>
      </div>

      <label className="field">
        <span>action</span>
        <select
          value={selectedAction}
          onChange={(event) => handleActionChange(event.target.value)}
          disabled={busy}
        >
          {state.allowed_actions.map((option) => (
            <option key={option.action} value={option.action}>
              {option.action}
            </option>
          ))}
        </select>
      </label>

      {requiredArgs.map((argKey) => {
        const allowedValues = selectedOption?.allowed_values[argKey];
        if (Array.isArray(allowedValues) && allowedValues.length > 0) {
          return (
            <label key={argKey} className="field">
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
          <label key={argKey} className="field">
            <span>{argKey}</span>
            <input
              value={String(args[argKey] ?? "")}
              onChange={(event) => handleArgChange(argKey, event.target.value)}
              disabled={busy}
            />
          </label>
        );
      })}

      <div className="action-buttons">
        <button
          type="button"
          className="btn-primary"
          disabled={busy || !selectedAction}
          onClick={() => onSubmitAction(selectedAction, args)}
        >
          提交动作
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={() => onTriggerAgent()}
        >
          Agent 决策
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={() => onAutoPlayAgents()}
        >
          AI 自动推进
        </button>
      </div>
      <p className="muted">所有动作均由后端白名单与参数校验判定。</p>
    </section>
  );
};

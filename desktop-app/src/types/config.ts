export interface Config {
  setup_complete: boolean;
  setup_step: number;
  t212_api_key: string;
  t212_api_secret: string;
  t212_env: "demo" | "live";
  t212_account_type: "invest" | "cfd";
  ai_provider: "anthropic" | "openai" | "azure" | "gemini" | "deepseek" | "ollama";
  ai_api_key: string;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_open_positions: number;
  max_position_size_pct: number;
  watchlist: string[];
}

export const DEFAULT_CONFIG: Config = {
  setup_complete: false,
  setup_step: 0,
  t212_api_key: "",
  t212_api_secret: "",
  t212_env: "demo",
  t212_account_type: "invest",
  ai_provider: "anthropic",
  ai_api_key: "",
  stop_loss_pct: 0.02,
  take_profit_pct: 0.04,
  max_open_positions: 10,
  max_position_size_pct: 0.05,
  watchlist: ["AAPL","TSLA","NVDA","MSFT","AMZN","GOOGL","META","AMD","JPM","V","UBER","PLTR"],
};

export const AI_PROVIDERS: {
  value: Config["ai_provider"];
  label: string;
  keyLabel: string;
  keyPlaceholder: string;
}[] = [
  { value: "anthropic", label: "Anthropic (Claude)", keyLabel: "Anthropic API Key", keyPlaceholder: "sk-ant-api03-..." },
  { value: "openai",    label: "OpenAI",             keyLabel: "OpenAI API Key",    keyPlaceholder: "sk-proj-..."     },
  { value: "azure",     label: "Azure AI",           keyLabel: "Azure AI Key",      keyPlaceholder: "your-azure-key" },
  { value: "gemini",    label: "Google Gemini",      keyLabel: "Gemini API Key",    keyPlaceholder: "AIza..."         },
  { value: "deepseek",  label: "DeepSeek",           keyLabel: "DeepSeek API Key",  keyPlaceholder: "sk-..."          },
  { value: "ollama",    label: "Ollama (local)",     keyLabel: "Ollama Base URL",   keyPlaceholder: "http://localhost:11434" },
];

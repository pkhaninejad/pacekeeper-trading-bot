export interface Config {
  setup_complete: boolean;
  setup_step: number;
  t212_api_key: string;
  t212_api_secret: string;
  t212_env: "demo" | "live";
  t212_account_type: "invest" | "cfd";
  ai_provider: "anthropic" | "openai" | "azure" | "gemini" | "deepseek" | "ollama";
  ai_api_key: string;
  ai_model: string;
  azure_endpoint: string;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_open_positions: number;
  max_position_size_pct: number;
  watchlist: string[];
  license_key: string;
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
  ai_model: "claude-sonnet-4-6",
  azure_endpoint: "",
  stop_loss_pct: 0.02,
  take_profit_pct: 0.04,
  max_open_positions: 10,
  max_position_size_pct: 0.05,
  watchlist: ["AAPL","TSLA","NVDA","MSFT","AMZN","GOOGL","META","AMD","JPM","V","UBER","PLTR"],
  license_key: "",
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

// Empty array = free-text input (deployment name / model name)
export const AI_PROVIDER_MODELS: Record<Config["ai_provider"], { value: string; label: string }[]> = {
  anthropic: [
    { value: "claude-opus-4-7",           label: "Claude Opus 4.7" },
    { value: "claude-sonnet-4-6",         label: "Claude Sonnet 4.6 (recommended)" },
    { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
  ],
  openai: [
    { value: "gpt-4o",      label: "GPT-4o (recommended)" },
    { value: "gpt-4o-mini", label: "GPT-4o mini" },
    { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
    { value: "o1-mini",     label: "o1 mini" },
  ],
  azure: [],    // deployment name — typed by user
  gemini: [
    { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash (recommended)" },
    { value: "gemini-1.5-pro",   label: "Gemini 1.5 Pro" },
    { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash" },
  ],
  deepseek: [
    { value: "deepseek-chat",     label: "DeepSeek Chat (recommended)" },
    { value: "deepseek-reasoner", label: "DeepSeek Reasoner (R1)" },
  ],
  ollama: [],   // model name — typed by user
};

export function defaultModel(provider: Config["ai_provider"]): string {
  const models = AI_PROVIDER_MODELS[provider];
  return models.length > 0 ? models[0].value : "";
}

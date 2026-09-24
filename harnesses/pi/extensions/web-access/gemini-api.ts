import { existsSync, readFileSync } from "node:fs";
import { getWebSearchConfigPath } from "./utils.ts";

const DEFAULT_API_HOST = "https://generativelanguage.googleapis.com";
const API_VERSION = "v1beta";
export const API_BASE = `${DEFAULT_API_HOST}/${API_VERSION}`;
const CONFIG_PATH = getWebSearchConfigPath();
export const DEFAULT_MODEL = "gemini-3-flash-preview";

interface GeminiApiConfig {
	geminiApiKey?: unknown;
	geminiBaseUrl?: unknown;
	cloudflareApiKey?: unknown;
}

let cachedConfig: GeminiApiConfig | null = null;

function loadConfig(): GeminiApiConfig {
	if (cachedConfig) return cachedConfig;
	if (!existsSync(CONFIG_PATH)) {
		cachedConfig = {};
		return cachedConfig;
	}

	const raw = readFileSync(CONFIG_PATH, "utf-8");
	try {
		cachedConfig = JSON.parse(raw) as GeminiApiConfig;
		return cachedConfig;
	} catch (err) {
		const message = err instanceof Error ? err.message : String(err);
		throw new Error(`Failed to parse ${CONFIG_PATH}: ${message}`);
	}
}

function withTimeout(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
	const timeout = AbortSignal.timeout(timeoutMs);
	return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

function normalizeApiKey(value: unknown): string | null {
	if (typeof value !== "string") return null;
	const normalized = value.trim();
	return normalized.length > 0 ? normalized : null;
}

function normalizeBaseUrl(value: unknown): string | null {
	if (typeof value !== "string") return null;
	const normalized = value.trim().replace(/\/+$/, "");
	return normalized.length > 0 ? normalized : null;
}

function isCloudflareGateway(): boolean {
	return getApiHost().includes("gateway.ai.cloudflare.com");
}

export function getApiKey(): string | null {
	return normalizeApiKey(process.env.GEMINI_API_KEY) ?? normalizeApiKey(loadConfig().geminiApiKey);
}

export function getApiHost(): string {
	return (
		normalizeBaseUrl(process.env.GOOGLE_GEMINI_BASE_URL) ??
		normalizeBaseUrl(loadConfig().geminiBaseUrl) ??
		DEFAULT_API_HOST
	);
}

export function getVersionedApiBase(): string {
	return `${getApiHost()}/${API_VERSION}`;
}

export function buildKeyParam(apiKey: string | null): string {
	if (!apiKey || isCloudflareGateway()) return "";
	return `?key=${apiKey}`;
}

export function getCloudflareApiKey(): string | null {
	return normalizeApiKey(process.env.CLOUDFLARE_API_KEY) ?? normalizeApiKey(loadConfig().cloudflareApiKey);
}

export function isGatewayConfigured(): boolean {
	return isCloudflareGateway() && getCloudflareApiKey() !== null;
}

export function buildAuthHeaders(): Record<string, string> {
	if (!isCloudflareGateway()) return {};
	const cloudflareApiKey = getCloudflareApiKey();
	return cloudflareApiKey ? { "cf-aig-authorization": `Bearer ${cloudflareApiKey}` } : {};
}

export function isGeminiApiAvailable(): boolean {
	return getApiKey() !== null || isGatewayConfigured();
}

export interface GeminiApiOptions {
	model?: string;
	mimeType?: string;
	signal?: AbortSignal;
	timeoutMs?: number;
}

export async function queryGeminiApiWithVideo(
	prompt: string,
	videoUri: string,
	options: GeminiApiOptions = {},
): Promise<string> {
	const apiKey = getApiKey();
	if (!apiKey && !isGatewayConfigured()) {
		throw new Error(
			"Gemini API not configured. Either:\n" +
			`  1. Set GEMINI_API_KEY in ${CONFIG_PATH}\n` +
			"  2. Set GOOGLE_GEMINI_BASE_URL + CLOUDFLARE_API_KEY for Cloudflare AI Gateway routing"
		);
	}

	const model = options.model ?? DEFAULT_MODEL;
	const signal = withTimeout(options.signal, options.timeoutMs ?? 120000);
	const url = `${getVersionedApiBase()}/models/${model}:generateContent${buildKeyParam(apiKey)}`;

	const fileData: Record<string, string> = { fileUri: videoUri };
	if (options.mimeType) fileData.mimeType = options.mimeType;

	const body = {
		contents: [
			{
				role: "user",
				parts: [
					{ fileData },
					{ text: prompt },
				],
			},
		],
	};

	const res = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json", ...buildAuthHeaders() },
		body: JSON.stringify(body),
		signal,
	});

	if (!res.ok) {
		const errorText = await res.text();
		throw new Error(`Gemini API error ${res.status}: ${errorText.slice(0, 300)}`);
	}

	const data = (await res.json()) as GenerateContentResponse;
	const text = data.candidates?.[0]?.content?.parts
		?.map((p) => p.text)
		.filter(Boolean)
		.join("\n");

	if (!text) throw new Error("Gemini API returned empty response");
	return text;
}

interface GenerateContentResponse {
	candidates?: Array<{
		content?: {
			parts?: Array<{ text?: string }>;
		};
	}>;
}

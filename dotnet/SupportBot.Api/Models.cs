using System.Text.Json.Serialization;

namespace SupportBot.Api;

// ----- Public API contract (what the widget sends/receives) -----------------
public record Turn(string Role, string Text);

public record ChatRequest(string Message, string Product, List<Turn>? History);

public record Source(string Title, string Url);

public record ChatResponse(string Answer, List<Source> Sources, bool Answered);

// ----- Options bound from appsettings.json ("SupportBot" section) ------------
public class SupportBotOptions
{
    public string Model { get; set; } = "gemini-3.1-flash-lite";
    /// <summary>fileSearchStores/xxxx. If blank, read from the manifest's "_store".</summary>
    public string? FileSearchStoreName { get; set; }
    /// <summary>Path to manifest.json produced by the Python kb_sync.py.</summary>
    public string ManifestPath { get; set; } = "manifest.json";
    /// <summary>"all" | "scoped" | "strict"</summary>
    public string ProductFilterMode { get; set; } = "all";
    public string[] AllowedOrigins { get; set; } = Array.Empty<string>();
    /// <summary>Prefer the GEMINI_API_KEY environment variable over this.</summary>
    public string? ApiKey { get; set; }
    /// <summary>Apps a user can launch the bot inside (the widget passes one).</summary>
    public string[] LaunchProducts { get; set; } = { "scorecard", "compyle" };
}

// ----- Gemini REST response DTOs (camelCase JSON) ---------------------------
public class GeminiResponse
{
    [JsonPropertyName("candidates")] public List<Candidate>? Candidates { get; set; }
}

public class Candidate
{
    [JsonPropertyName("content")] public ContentDto? Content { get; set; }
    [JsonPropertyName("groundingMetadata")] public GroundingMetadata? GroundingMetadata { get; set; }
}

public class ContentDto
{
    [JsonPropertyName("parts")] public List<PartDto>? Parts { get; set; }
}

public class PartDto
{
    [JsonPropertyName("text")] public string? Text { get; set; }
}

public class GroundingMetadata
{
    [JsonPropertyName("groundingChunks")] public List<GroundingChunk>? GroundingChunks { get; set; }
}

public class GroundingChunk
{
    [JsonPropertyName("retrievedContext")] public RetrievedContext? RetrievedContext { get; set; }
}

public class RetrievedContext
{
    // For File Search, "title" carries the file's display_name (our article id).
    [JsonPropertyName("title")] public string? Title { get; set; }
    [JsonPropertyName("uri")] public string? Uri { get; set; }
    [JsonPropertyName("text")] public string? Text { get; set; }
    [JsonPropertyName("documentName")] public string? DocumentName { get; set; }
    [JsonPropertyName("customMetadata")] public List<CustomMeta>? CustomMetadata { get; set; }
}

public class CustomMeta
{
    [JsonPropertyName("key")] public string? Key { get; set; }
    [JsonPropertyName("stringValue")] public string? StringValue { get; set; }
    [JsonPropertyName("numericValue")] public double? NumericValue { get; set; }
}

// ----- Manifest DTOs (manifest.json from kb_sync.py) ------------------------
public class Manifest
{
    [JsonPropertyName("_store")] public string? Store { get; set; }
    [JsonPropertyName("articles")] public Dictionary<string, ArticleRecord> Articles { get; set; } = new();
}

public class ArticleRecord
{
    [JsonPropertyName("title")] public string? Title { get; set; }
    [JsonPropertyName("url")] public string? Url { get; set; }
    [JsonPropertyName("product")] public string? Product { get; set; }
    [JsonPropertyName("doc_name")] public string? DocName { get; set; }
}

using System.Net.Http.Json;
using System.Text.Json;

namespace SupportBot.Api;

public record GeminiResult(string Text, List<GroundingChunk> Chunks);

/// <summary>
/// Thin client over the Gemini REST API's generateContent endpoint with the
/// File Search tool. There is no official Google .NET SDK, so we call REST directly.
/// </summary>
public class GeminiClient
{
    private readonly HttpClient _http;
    private readonly SupportBotOptions _opts;
    private readonly string _apiKey;

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
    };

    public GeminiClient(HttpClient http, SupportBotOptions opts)
    {
        _http = http;
        _opts = opts;
        _apiKey = Environment.GetEnvironmentVariable("GEMINI_API_KEY")
                  ?? opts.ApiKey
                  ?? throw new InvalidOperationException(
                      "Set the GEMINI_API_KEY environment variable (or SupportBot:ApiKey).");
        if (_http.BaseAddress is null)
            _http.BaseAddress = new Uri("https://generativelanguage.googleapis.com/");
    }

    public async Task<GeminiResult> GenerateAsync(
        string systemInstruction,
        IEnumerable<Turn> history,
        string message,
        string storeName,
        string? metadataFilter,
        CancellationToken ct = default)
    {
        // Build conversation contents (recent turns + the new question).
        var contents = new List<object>();
        foreach (var turn in history.TakeLast(6))
        {
            var role = turn.Role == "model" ? "model" : "user";
            contents.Add(new { role, parts = new[] { new { text = turn.Text } } });
        }
        contents.Add(new { role = "user", parts = new[] { new { text = message } } });

        // File Search tool config (omit metadataFilter in "all" mode).
        var fileSearch = new Dictionary<string, object>
        {
            ["fileSearchStoreNames"] = new[] { storeName },
        };
        if (!string.IsNullOrEmpty(metadataFilter))
            fileSearch["metadataFilter"] = metadataFilter;

        var body = new
        {
            systemInstruction = new { parts = new[] { new { text = systemInstruction } } },
            contents,
            tools = new object[] { new { fileSearch } },
            generationConfig = new { temperature = 0.2 },
        };

        var url = $"v1beta/models/{_opts.Model}:generateContent";
        using var req = new HttpRequestMessage(HttpMethod.Post, url)
        {
            Content = JsonContent.Create(body, options: JsonOpts),
        };
        req.Headers.Add("x-goog-api-key", _apiKey);

        using var resp = await _http.SendAsync(req, ct);
        var raw = await resp.Content.ReadAsStringAsync(ct);
        if (!resp.IsSuccessStatusCode)
            throw new HttpRequestException($"Gemini API {(int)resp.StatusCode}: {raw}");

        var parsed = JsonSerializer.Deserialize<GeminiResponse>(raw, JsonOpts);
        var candidate = parsed?.Candidates?.FirstOrDefault();

        var text = string.Join("",
            candidate?.Content?.Parts?.Select(p => p.Text) ?? Enumerable.Empty<string?>()).Trim();
        var chunks = candidate?.GroundingMetadata?.GroundingChunks ?? new List<GroundingChunk>();

        return new GeminiResult(text, chunks);
    }
}

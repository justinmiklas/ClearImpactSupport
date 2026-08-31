using SupportBot.Api;

var builder = WebApplication.CreateBuilder(args);

// ----- Configuration --------------------------------------------------------
var options = builder.Configuration.GetSection("SupportBot").Get<SupportBotOptions>()
              ?? new SupportBotOptions();
builder.Services.AddSingleton(options);

// Resolver loads manifest.json once (article links + the File Search store name).
builder.Services.AddSingleton<ManifestSourceResolver>();

// Typed HttpClient for Gemini (uses IHttpClientFactory pooling).
builder.Services.AddHttpClient<GeminiClient>();

// CORS: your real app domains (from appsettings) plus localhost/null for the
// local demo page. Lock this down to your product domains in production.
const string CorsPolicy = "supportbot";
builder.Services.AddCors(o => o.AddPolicy(CorsPolicy, p =>
{
    var dev = new[]
    {
        "null", "http://localhost", "http://127.0.0.1",
        "http://localhost:8000", "http://localhost:5173",
    };
    var origins = options.AllowedOrigins.Concat(dev).Distinct().ToArray();
    p.WithOrigins(origins).AllowAnyHeader().AllowAnyMethod();
}));

var app = builder.Build();
app.UseCors(CorsPolicy);

// ----- Endpoints ------------------------------------------------------------
app.MapPost("/chat", async (
    ChatRequest req,
    GeminiClient gemini,
    ManifestSourceResolver resolver,
    SupportBotOptions opts) =>
{
    if (string.IsNullOrWhiteSpace(req.Message))
        return Results.BadRequest("Message is required.");

    var product = (req.Product ?? "").ToLowerInvariant();
    if (!opts.LaunchProducts.Contains(product))
        return Results.BadRequest($"Unknown product '{req.Product}'.");

    var systemInstruction = SupportPrompt.BuildSystemInstruction(product);

    // Scope retrieval. "all" searches the whole knowledge base (recommended:
    // Scorecard, Compyle and Control integrate).
    string? metadataFilter = opts.ProductFilterMode switch
    {
        "strict" => $"product=\"{product}\"",
        "scoped" => $"product=\"{product}\" OR product=\"general\"",
        _        => null, // "all"
    };

    GeminiResult result;
    try
    {
        result = await gemini.GenerateAsync(
            systemInstruction, req.History ?? new(), req.Message,
            resolver.StoreName, metadataFilter);
    }
    catch (Exception ex)
    {
        return Results.Problem($"Model error: {ex.Message}", statusCode: 502);
    }

    var (sources, grounded) = resolver.Resolve(result.Chunks);

    // "Never make up answers" guardrail: refuse unless the answer is grounded.
    if (result.Text.Contains(SupportPrompt.NoAnswerSentinel)
        || !grounded
        || string.IsNullOrEmpty(result.Text))
    {
        return Results.Ok(new ChatResponse(SupportPrompt.RefusalMessage, new(), false));
    }

    return Results.Ok(new ChatResponse(result.Text, sources, true));
});

app.MapGet("/health", (ManifestSourceResolver resolver, SupportBotOptions opts) =>
    Results.Ok(new
    {
        status = "ok",
        model = opts.Model,
        store = resolver.StoreName,
        articlesIndexed = resolver.ArticleCount,
        filterMode = opts.ProductFilterMode,
    }));

app.Run();

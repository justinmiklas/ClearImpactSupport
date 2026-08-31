using System.Text.Json;

namespace SupportBot.Api;

/// <summary>
/// Loads manifest.json (produced by the Python kb_sync.py) and turns the model's
/// grounding chunks into verified article links. Resolving links from the manifest
/// — rather than trusting the model — guarantees every link points at a real,
/// indexed help-center article.
/// </summary>
public class ManifestSourceResolver
{
    private readonly Dictionary<string, ArticleRecord> _byId;       // article id
    private readonly Dictionary<string, ArticleRecord> _byDocName;  // doc resource name
    public string StoreName { get; }

    public ManifestSourceResolver(SupportBotOptions opts)
    {
        Manifest manifest;
        try
        {
            var json = File.ReadAllText(opts.ManifestPath);
            manifest = JsonSerializer.Deserialize<Manifest>(json) ?? new Manifest();
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException(
                $"Could not read manifest at '{opts.ManifestPath}'. Run the Python kb_sync.py " +
                $"first, then point SupportBot:ManifestPath at the generated manifest.json.", ex);
        }

        _byId = manifest.Articles;
        _byDocName = manifest.Articles.Values
            .Where(a => !string.IsNullOrEmpty(a.DocName))
            .GroupBy(a => a.DocName!)
            .ToDictionary(g => g.Key, g => g.First());

        StoreName = !string.IsNullOrWhiteSpace(opts.FileSearchStoreName)
            ? opts.FileSearchStoreName!
            : manifest.Store
              ?? throw new InvalidOperationException(
                  "No File Search store found. Set SupportBot:FileSearchStoreName or ensure " +
                  "manifest.json contains \"_store\".");
    }

    public int ArticleCount => _byId.Count;

    /// <summary>Returns (sources, grounded). grounded == any chunks were retrieved.</summary>
    public (List<Source> Sources, bool Grounded) Resolve(IEnumerable<GroundingChunk>? chunks)
    {
        if (chunks is null) return (new List<Source>(), false);

        var list = chunks.ToList();
        if (list.Count == 0) return (new List<Source>(), false);

        var seen = new HashSet<string>();
        var sources = new List<Source>();

        foreach (var chunk in list)
        {
            var rc = chunk.RetrievedContext;
            if (rc is null) continue;

            ArticleRecord? rec = null;

            // 1) display_name (our article id) usually arrives as title.
            if (rc.Title is not null && _byId.TryGetValue(rc.Title, out var byTitle))
                rec = byTitle;

            // 2) document resource name / uri.
            if (rec is null)
            {
                var docref = rc.DocumentName ?? rc.Uri;
                if (docref is not null && _byDocName.TryGetValue(docref, out var byDoc))
                    rec = byDoc;
            }

            // 3) custom metadata echoed back.
            string? url = rec?.Url, title = rec?.Title;
            if (rec is null && rc.CustomMetadata is not null)
            {
                url = rc.CustomMetadata.FirstOrDefault(m => m.Key == "url")?.StringValue;
                title = rc.CustomMetadata.FirstOrDefault(m => m.Key == "title")?.StringValue;
            }

            if (!string.IsNullOrEmpty(url) && seen.Add(url))
                sources.Add(new Source(title ?? url!, url!));
        }

        return (sources, true);
    }
}

using Microsoft.AspNetCore.HttpLogging;
using Metacache.Core.Cache;
using Metacache.Core.Matching;
using Metacache.Core.Providers;
using Metacache.Host;
using Metacache.Plex;
using Metacache.Plex.Warming;

var builder = WebApplication.CreateBuilder(args);

// The provider API is unauthenticated (Plex doesn't send auth yet), so default to
// loopback and let the user opt into LAN exposure via config/env:
//   Metacache__BindAddress=0.0.0.0  Metacache__Port=8765
var bindAddress = builder.Configuration["Metacache:BindAddress"] ?? "127.0.0.1";
var port = builder.Configuration.GetValue<int?>("Metacache:Port") ?? 8765;
builder.WebHost.UseUrls($"http://{bindAddress}:{port}");

// SQLite cache location (relative to the working directory unless overridden;
// ":memory:" is used by integration tests and must pass through untouched).
var dataPath = builder.Configuration["Metacache:DataPath"] ?? "data/metacache.db";
if (dataPath != ":memory:")
{
    dataPath = Path.GetFullPath(dataPath);
    Directory.CreateDirectory(Path.GetDirectoryName(dataPath)!);
}

// Cache stack: SQLite store + content-addressed image store (config under Metacache:Images).
var imagesSection = builder.Configuration.GetSection("Metacache:Images");
var cacheOptions = new CacheOptions(
    DataSource: dataPath,
    ImageDirectory: Path.GetFullPath(imagesSection["Directory"] ?? "data/images"),
    MaxImageBytes: imagesSection.GetValue<long?>("MaxFileBytes") ?? 20L * 1024 * 1024,
    MaxImageTotalBytes: imagesSection.GetValue<long?>("MaxTotalBytes") ?? 10L * 1024 * 1024 * 1024);
builder.Services.AddMetacacheCache(cacheOptions);
builder.Services.AddMetacacheMatching(builder.Configuration);

// TMDB client (Bearer-auth header, so the API key never appears in URLs/cache keys)
// and the provider services that answer Plex match/metadata requests (M1: movies).
var tmdbSection = builder.Configuration.GetSection("Metacache:Tmdb");
var tmdbAuth = Enum.TryParse<TmdbAuthMode>(tmdbSection["Auth"] ?? "Auto", ignoreCase: true, out var parsedAuth)
    ? parsedAuth
    : TmdbAuthMode.Auto;
var tmdbOptions = new TmdbOptions(
    ApiKey: tmdbSection["ApiKey"] ?? "",
    BaseUrl: tmdbSection["BaseUrl"] ?? "https://api.themoviedb.org/3",
    ImageBaseUrl: tmdbSection["ImageBaseUrl"] ?? "https://image.tmdb.org/t/p/original",
    Auth: tmdbAuth);
builder.Services.AddTmdbClient(tmdbOptions);
builder.Services.AddMetacachePlexProviders();

// M3 cache warming: Radarr/Sonarr become the inventory (DESIGN.md §8). A blank URL
// disables that source; the /warm/* endpoints and /metrics dashboard are mapped below.
var arrSection = builder.Configuration.GetSection("Metacache:Arr");
var arrOptions = new ArrOptions(
    RadarrUrl: arrSection["RadarrUrl"] ?? "",
    RadarrApiKey: arrSection["RadarrApiKey"] ?? "",
    SonarrUrl: arrSection["SonarrUrl"] ?? "",
    SonarrApiKey: arrSection["SonarrApiKey"] ?? "",
    Concurrency: arrSection.GetValue<int?>("Concurrency") ?? 4);
var warmSection = builder.Configuration.GetSection("Metacache:Warm");
var warmOptions = new WarmOptions(
    Enabled: warmSection.GetValue<bool?>("Enabled") ?? true,
    ScheduleTime: warmSection["ScheduleTime"] ?? "03:00");
builder.Services.AddMetacacheWarming(arrOptions, warmOptions);

builder.Services.AddHttpLogging(o =>
{
    o.LoggingFields = HttpLoggingFields.RequestPath
        | HttpLoggingFields.RequestQuery
        | HttpLoggingFields.ResponseStatusCode;
});

var app = builder.Build();

app.UseHttpLogging();
app.MapProviderEndpoints();
app.MapCacheAdminEndpoints();
app.MapImageEndpoints();
app.MapWarmEndpoints();
app.MapMetricsEndpoints();
app.MapMetricsDashboard();
app.MapGet("/healthz", () => Results.Text("ok", "text/plain"));

app.Run();

/// <summary>Exposed so integration tests can bootstrap the host via WebApplicationFactory.</summary>
public partial class Program;

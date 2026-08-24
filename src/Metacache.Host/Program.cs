using Microsoft.AspNetCore.HttpLogging;
using Metacache.Plex;

var builder = WebApplication.CreateBuilder(args);

// The provider API is unauthenticated (Plex doesn't send auth yet), so default to
// loopback and let the user opt into LAN exposure via config/env:
//   Metacache__BindAddress=0.0.0.0  Metacache__Port=8765
var bindAddress = builder.Configuration["Metacache:BindAddress"] ?? "127.0.0.1";
var port = builder.Configuration.GetValue<int?>("Metacache:Port") ?? 8765;
builder.WebHost.UseUrls($"http://{bindAddress}:{port}");

builder.Services.AddHttpLogging(o =>
{
    o.LoggingFields = HttpLoggingFields.RequestPath
        | HttpLoggingFields.RequestQuery
        | HttpLoggingFields.ResponseStatusCode;
});

var app = builder.Build();

app.UseHttpLogging();
app.MapProviderEndpoints();
app.MapGet("/healthz", () => Results.Text("ok", "text/plain"));

app.Run();

/// <summary>Exposed so integration tests can bootstrap the host via WebApplicationFactory.</summary>
public partial class Program;

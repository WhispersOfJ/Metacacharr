using Metacache.Pages;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;

namespace Metacache.Host.Pages;

/// <summary>
/// Serves the 10 UI/UX improvement pages as self-contained HTML with zero external
/// dependencies. Each page is a complete SPA that polls the existing API endpoints.
/// </summary>
public static class PagesEndpoints
{
    public static void MapPages(this WebApplication app)
    {
        app.MapGet("/ui/setup", () => Results.Content(SetupWizard.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/health", () => Results.Content(ProviderHealth.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/freshness", () => Results.Content(CacheFreshness.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/register", () => Results.Content(PlexRegistration.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/matches", () => Results.Content(MatchPanel.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/guid", () => Results.Content(GuidExplorer.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/overrides", () => Results.Content(OverrideEditor.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/warm-calendar", () => Results.Content(WarmCalendar.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/warm-progress", () => Results.Content(WarmProgress.Page, "text/html; charset=utf-8"));
        app.MapGet("/ui/cache-diff", () => Results.Content(CacheDiff.Page, "text/html; charset=utf-8"));
    }
}

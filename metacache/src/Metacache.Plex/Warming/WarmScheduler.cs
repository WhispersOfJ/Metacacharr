using System.Globalization;

namespace Metacache.Plex.Warming;

/// <summary>Computes when the next scheduled warm runs (pure logic, unit-testable).</summary>
public static class WarmScheduler
{
    /// <summary>
    /// Next occurrence of the daily schedule after (or at) <paramref name="now"/>.
    /// Accepts "HH:mm" or "HH:mm:ss"; throws on unparseable input.
    /// </summary>
    public static DateTimeOffset NextRunTime(string scheduleTime, DateTimeOffset now)
    {
        TimeSpan timeOfDay = ParseTimeOfDay(scheduleTime);
        var today = new DateTimeOffset(
            now.Year, now.Month, now.Day,
            timeOfDay.Hours, timeOfDay.Minutes, timeOfDay.Seconds, now.Offset);
        return today >= now ? today : today.AddDays(1);
    }

    private static TimeSpan ParseTimeOfDay(string scheduleTime)
    {
        if (string.IsNullOrWhiteSpace(scheduleTime))
            throw new ArgumentException("Warm schedule time must be 'HH:mm' (e.g. \"03:00\").", nameof(scheduleTime));
        if (TimeSpan.TryParse(scheduleTime, CultureInfo.InvariantCulture, out TimeSpan timeOfDay)
            && timeOfDay >= TimeSpan.Zero && timeOfDay < TimeSpan.FromDays(1))
            return timeOfDay;
        throw new ArgumentException($"Invalid warm schedule time '{scheduleTime}' (expected 'HH:mm', e.g. \"03:00\").", nameof(scheduleTime));
    }
}

using Metacache.Core.Matching;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Metacache.Host.Tests.Matching;

public class MatchPolicyConfigurationTests
{
    [Fact]
    public void Binds_policy_from_configuration_section()
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Metacache:Matching:AutoMatchThreshold"] = "0.75",
                ["Metacache:Matching:TvStructureWeight"] = "0.5",
                ["Metacache:Matching:MaxManualResults"] = "5"
            })
            .Build();

        using var provider = new ServiceCollection()
            .AddMetacacheMatching(config)
            .BuildServiceProvider();

        MatchPolicy policy = provider.GetRequiredService<MatchPolicy>();

        Assert.Equal(0.75, policy.AutoMatchThreshold);
        Assert.Equal(0.5, policy.TvStructureWeight);
        Assert.Equal(5, policy.MaxManualResults);
        Assert.Equal(MatchPolicy.Default.TitleWeight, policy.TitleWeight); // unspecified keys keep defaults
    }

    [Fact]
    public void Falls_back_to_defaults_when_section_is_absent()
    {
        using var provider = new ServiceCollection()
            .AddMetacacheMatching(new ConfigurationBuilder().Build())
            .BuildServiceProvider();

        Assert.Equal(MatchPolicy.Default, provider.GetRequiredService<MatchPolicy>());
    }

    [Fact]
    public void Host_binds_appsettings_and_accepts_overrides()
    {
        using var factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(b => b.UseSetting("Metacache:Matching:AutoMatchThreshold", "0.75"));

        MatchPolicy policy = factory.Services.GetRequiredService<MatchPolicy>();

        Assert.Equal(0.75, policy.AutoMatchThreshold);    // host setting wins
        Assert.Equal(0.35, policy.TvStructureWeight);     // untouched, from appsettings.json
        Assert.Equal(20, policy.MaxManualResults);        // untouched, from appsettings.json
    }
}

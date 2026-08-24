# syntax=docker/dockerfile:1
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish src/Metacache.Host/Metacache.Host.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
# Expose the provider API on the LAN (Plex registers this host:port as its provider URL).
ENV Metacache__BindAddress=0.0.0.0
EXPOSE 8765
ENTRYPOINT ["dotnet", "Metacache.Host.dll"]

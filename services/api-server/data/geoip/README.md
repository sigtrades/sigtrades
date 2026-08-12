# GeoLite2 mmdb（可选）

将 MaxMind GeoLite2 数据库放到仓库根目录 `data/geoip/` 以启用 IP → 国家/省份解析（无 Cloudflare 头时）：

- `GeoLite2-City.mmdb`（推荐，含国家+省份）
- `GeoLite2-Country.mmdb`（仅国家）

下载：`make download-geoip MAXMIND_LICENSE_KEY=your_key`

Docker 通过 volume 挂载：

```yaml
volumes:
  - ./data/geoip:/app/data/geoip:ro
```

环境变量见根目录 `.env.example` 中的 `GEOIP2_*`。

Cloudflare 代理下会优先使用 `CF-IPCountry` 头，无需 mmdb 也能显示国家码。

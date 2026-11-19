const showcaseOrigin = 'http://127.0.0.1:8090'
const workbenchRoutes = ['/dashboard/session/:id', '/dashboard-assets/:path*', '/api/:path*', '/dashboard/reviewer', '/dashboard/settings', '/dashboard/campaigns', '/dashboard/run/:id']
module.exports = {
  devIndicators: false,
  turbopack: { root: __dirname },
  async rewrites() {
    return workbenchRoutes.map(source => ({ source, destination: showcaseOrigin + source }))
  },
}

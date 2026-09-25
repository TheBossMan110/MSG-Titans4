/** @type {import('next').NextConfig} */
const nextConfig = {
  // The build is the gate. Type errors do not ship.
  typescript: { ignoreBuildErrors: false },
  // Static assets only; no remote image optimisation to configure or break.
  images: { unoptimized: true },
  // Three.js and friends are ESM and large; let Turbopack tree-shake them.
  transpilePackages: ['three'],
}

export default nextConfig

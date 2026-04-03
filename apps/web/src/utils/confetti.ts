const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#34d399', '#fbbf24']
const PARTICLE_COUNT = 40
const LIFETIME_MS = 2500

export function spawnConfetti(): void {
  const container = document.body
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const particle = document.createElement('div')
    particle.className = 'confetti-particle'
    particle.style.backgroundColor = COLORS[Math.floor(Math.random() * COLORS.length)]
    particle.style.left = `${Math.random() * 100}vw`
    particle.style.top = `${60 + Math.random() * 30}vh`
    particle.style.transform = `rotate(${Math.random() * 360}deg)`
    particle.style.animation = `confetti ${1 + Math.random() * 1.5}s ease-out forwards`
    particle.style.width = `${6 + Math.random() * 6}px`
    particle.style.height = `${6 + Math.random() * 6}px`
    container.appendChild(particle)
    setTimeout(() => particle.remove(), LIFETIME_MS)
  }
}

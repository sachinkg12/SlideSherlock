import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Play, Pause, Volume2, Volume1, VolumeX, Maximize } from 'lucide-react'

interface VideoPlayerProps {
  src: string
  title: string
}

function VideoPlayer({ src, title }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [volume, setVolume] = useState(1)
  const [showVolume, setShowVolume] = useState(false)
  const [showOverlay, setShowOverlay] = useState(true)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState('0:00')
  const volumeTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  const togglePlay = () => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) {
      v.play()
      setIsPlaying(true)
      setShowOverlay(false)
    } else {
      v.pause()
      setIsPlaying(false)
    }
  }

  const toggleMute = () => {
    const v = videoRef.current
    if (!v) return
    v.muted = !v.muted
    setIsMuted(v.muted)
    if (!v.muted && v.volume === 0) {
      v.volume = 0.5
      setVolume(0.5)
    }
  }

  const handleVolumeChange = (e: React.MouseEvent<HTMLDivElement>) => {
    const v = videoRef.current
    if (!v) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    v.volume = pct
    setVolume(pct)
    v.muted = pct === 0
    setIsMuted(pct === 0)
  }

  const handleVolumeDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    const bar = e.currentTarget
    const onMove = (ev: MouseEvent) => {
      const v = videoRef.current
      if (!v) return
      const rect = bar.getBoundingClientRect()
      const pct = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
      v.volume = pct
      setVolume(pct)
      v.muted = pct === 0
      setIsMuted(pct === 0)
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const showVolumeSlider = () => {
    if (volumeTimeout.current) clearTimeout(volumeTimeout.current)
    setShowVolume(true)
  }

  const hideVolumeSlider = () => {
    volumeTimeout.current = setTimeout(() => setShowVolume(false), 500)
  }

  const VolumeIcon = isMuted || volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2

  const handleFullscreen = () => {
    videoRef.current?.requestFullscreen()
  }

  const handleTimeUpdate = () => {
    const v = videoRef.current
    if (!v || !v.duration) return
    setProgress((v.currentTime / v.duration) * 100)
  }

  const handleLoadedMetadata = () => {
    const v = videoRef.current
    if (!v) return
    const mins = Math.floor(v.duration / 60)
    const secs = Math.floor(v.duration % 60)
    setDuration(`${mins}:${secs.toString().padStart(2, '0')}`)
  }

  const seekTo = (e: React.MouseEvent<HTMLDivElement> | MouseEvent, el: HTMLDivElement) => {
    const v = videoRef.current
    if (!v || !v.duration) return
    const rect = el.getBoundingClientRect()
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    v.currentTime = pct * v.duration
  }

  const progressBarRef = useRef<HTMLDivElement>(null)

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    seekTo(e, e.currentTarget)
  }

  const handleSeekDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    const bar = e.currentTarget
    const onMove = (ev: MouseEvent) => seekTo(ev, bar)
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const handleEnded = () => {
    setIsPlaying(false)
    setShowOverlay(true)
  }

  return (
    <div className="glass-card overflow-hidden">
      <div
        className="relative aspect-video cursor-pointer bg-[var(--color-bg)]"
        onClick={togglePlay}
        onMouseEnter={() => !showOverlay && setShowOverlay(true)}
        onMouseLeave={() => isPlaying && setShowOverlay(false)}
      >
        <video
          ref={videoRef}
          src={src}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
          className="h-full w-full"
          playsInline
          preload="metadata"
          aria-label={`Video: ${title}`}
        />

        {/* Big play button overlay */}
        <AnimatePresence>
          {showOverlay && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center bg-[var(--color-bg)]/30"
            >
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                className="flex h-20 w-20 items-center justify-center rounded-full bg-[var(--color-surface)] backdrop-blur-md border border-border-subtle"
                aria-label={isPlaying ? 'Pause video' : 'Play video'}
              >
                {isPlaying ? (
                  <Pause className="h-8 w-8 text-white" />
                ) : (
                  <Play className="ml-1 h-8 w-8 text-white" />
                )}
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Controls bar */}
      <div className="flex items-center gap-4 px-5 py-3">
        <button
          onClick={togglePlay}
          className="text-text-primary hover:text-indigo-400 transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <Pause className="h-5 w-5" />
          ) : (
            <Play className="h-5 w-5" />
          )}
        </button>

        {/* Progress bar */}
        <div
          className="flex-1 h-2 rounded-full bg-[var(--color-surface)] cursor-pointer group relative"
          onClick={handleSeek}
          onMouseDown={handleSeekDrag}
          ref={progressBarRef}
          role="slider"
          aria-label="Video progress"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          tabIndex={0}
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-[width] duration-150 pointer-events-none relative"
            style={{ width: `${progress}%` }}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 h-3.5 w-3.5 rounded-full bg-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </div>

        <span className="text-sm text-text-secondary tabular-nums min-w-[4ch]">
          {duration}
        </span>

        {/* Volume control */}
        <div
          className="relative flex items-center"
          onMouseEnter={showVolumeSlider}
          onMouseLeave={hideVolumeSlider}
        >
          <button
            onClick={toggleMute}
            className="text-text-primary hover:text-indigo-400 transition-colors"
            aria-label={isMuted ? 'Unmute' : 'Mute'}
          >
            <VolumeIcon className="h-5 w-5" />
          </button>

          <AnimatePresence>
            {showVolume && (
              <motion.div
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 80, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="overflow-hidden ml-2"
              >
                <div
                  className="h-1.5 w-20 rounded-full bg-[var(--color-surface)] cursor-pointer group relative"
                  onClick={handleVolumeChange}
                  onMouseDown={handleVolumeDrag}
                  role="slider"
                  aria-label="Volume"
                  aria-valuenow={Math.round(volume * 100)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-indigo-500 pointer-events-none relative"
                    style={{ width: `${(isMuted ? 0 : volume) * 100}%` }}
                  >
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 h-3 w-3 rounded-full bg-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <button
          onClick={handleFullscreen}
          className="text-text-primary hover:text-indigo-400 transition-colors"
          aria-label="Fullscreen"
        >
          <Maximize className="h-5 w-5" />
        </button>
      </div>

      {/* Title */}
      <div className="px-5 pb-4">
        <p className="text-base text-text-secondary">{title}</p>
      </div>
    </div>
  )
}

export default VideoPlayer

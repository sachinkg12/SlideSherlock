import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Play, Pause, Volume2, VolumeX, Maximize } from 'lucide-react'

interface VideoPlayerProps {
  src: string
  title: string
}

function VideoPlayer({ src, title }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [showOverlay, setShowOverlay] = useState(true)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState('0:00')

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
  }

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

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const v = videoRef.current
    if (!v) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    v.currentTime = pct * v.duration
  }

  const handleEnded = () => {
    setIsPlaying(false)
    setShowOverlay(true)
  }

  return (
    <div className="glass-card overflow-hidden">
      <div
        className="relative aspect-video cursor-pointer bg-black"
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
              className="absolute inset-0 flex items-center justify-center bg-black/30"
            >
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                className="flex h-20 w-20 items-center justify-center rounded-full bg-white/10 backdrop-blur-md border border-white/20"
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
          className="flex-1 h-1.5 rounded-full bg-white/10 cursor-pointer group"
          onClick={handleSeek}
          role="slider"
          aria-label="Video progress"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          tabIndex={0}
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-150 group-hover:h-2.5 relative"
            style={{ width: `${progress}%` }}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 h-3 w-3 rounded-full bg-white opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </div>

        <span className="text-sm text-text-secondary tabular-nums min-w-[4ch]">
          {duration}
        </span>

        <button
          onClick={toggleMute}
          className="text-text-primary hover:text-indigo-400 transition-colors"
          aria-label={isMuted ? 'Unmute' : 'Mute'}
        >
          {isMuted ? (
            <VolumeX className="h-5 w-5" />
          ) : (
            <Volume2 className="h-5 w-5" />
          )}
        </button>

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

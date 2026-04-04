import { useState, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileUp, CheckCircle2, AlertCircle } from 'lucide-react'

interface DropZoneProps {
  file: File | null
  onFileSelect: (file: File) => void
}

function DropZone({ file, onFileSelect }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isInvalid, setIsInvalid] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const validateAndSet = useCallback(
    (f: File) => {
      if (!f.name.toLowerCase().endsWith('.pptx')) {
        setIsInvalid(true)
        setTimeout(() => setIsInvalid(false), 1000)
        return
      }
      onFileSelect(f)
    },
    [onFileSelect],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const dropped = e.dataTransfer.files[0]
      if (dropped) validateAndSet(dropped)
    },
    [validateAndSet],
  )

  const handleClick = () => inputRef.current?.click()

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) validateAndSet(selected)
  }

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="file"
        accept=".pptx"
        onChange={handleChange}
        className="hidden"
        aria-label="Upload presentation file"
      />

      <AnimatePresence mode="wait">
        {file ? (
          <motion.div
            key="file-selected"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            onClick={handleClick}
            className="glass-card-hover flex cursor-pointer items-center gap-4 px-6 py-5"
            role="button"
            tabIndex={0}
            aria-label="Change selected file"
          >
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', delay: 0.1 }}
            >
              <CheckCircle2 className="h-8 w-8 text-emerald-400" />
            </motion.div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg font-medium text-text-primary">
                {file.name}
              </p>
              <p className="text-sm text-text-secondary">
                {formatSize(file.size)} — Click to change
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="drop-area"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            onClick={handleClick}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            whileHover={{ scale: 1.02 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            className={`
              relative flex cursor-pointer flex-col items-center justify-center
              rounded-2xl border-2 border-dashed px-8 py-16 text-center
              transition-colors duration-300 backdrop-blur-xl
              ${
                isInvalid
                  ? 'animate-shake border-status-error/60 bg-status-error/5'
                  : isDragging
                    ? 'border-indigo-400/60 bg-indigo-500/5'
                    : 'border-border-subtle bg-surface hover:border-indigo-400/40 hover:bg-surface-hover'
              }
            `}
            role="button"
            tabIndex={0}
            aria-label="Drop your presentation file here or click to browse"
          >
            {/* Ambient glow behind drop zone */}
            <div
              className="pointer-events-none absolute inset-0 rounded-2xl"
              style={{
                background: isDragging
                  ? 'radial-gradient(ellipse at center, rgba(99, 102, 241, 0.1) 0%, transparent 70%)'
                  : 'radial-gradient(ellipse at center, rgba(99, 102, 241, 0.04) 0%, transparent 70%)',
              }}
            />

            <motion.div
              animate={
                isDragging
                  ? { y: -8, scale: 1.1 }
                  : { y: [0, -4, 0] }
              }
              transition={
                isDragging
                  ? { type: 'spring' }
                  : { duration: 3, repeat: Infinity, ease: 'easeInOut' }
              }
              className="relative"
            >
              {isInvalid ? (
                <AlertCircle className="h-14 w-14 text-status-error" />
              ) : (
                <FileUp className="h-14 w-14 text-indigo-400/70" />
              )}
            </motion.div>

            <p className="relative mt-6 text-xl font-medium text-text-primary">
              {isInvalid
                ? 'Only .pptx files are accepted'
                : 'Drop your presentation here'}
            </p>
            <p className="relative mt-2 text-base text-text-secondary">
              {isInvalid ? 'Please try again with a PowerPoint file' : 'or click to browse'}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default DropZone

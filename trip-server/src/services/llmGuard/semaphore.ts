export class Semaphore {
  private current = 0

  constructor(private max: number) {}

  tryAcquire(): boolean {
    if (this.current >= this.max) return false
    this.current++
    return true
  }

  release(): void {
    if (this.current > 0) this.current--
  }

  get available(): number {
    return this.max - this.current
  }
}

export class ConcurrencyGuard {
  private global: Semaphore
  private perUser = new Map<string | number, { sem: Semaphore; refs: number }>()
  private cleanupInterval: ReturnType<typeof setInterval>

  constructor(globalMax: number, private perUserMax: number) {
    this.global = new Semaphore(globalMax)
    this.cleanupInterval = setInterval(() => this.cleanup(), 60_000)
    if (this.cleanupInterval.unref) this.cleanupInterval.unref()
  }

  tryAcquire(userId: string | number | null): { success: boolean; release: () => void } {
    let userSlot = false
    let userSem: Semaphore | null = null

    if (userId != null) {
      let entry = this.perUser.get(userId)
      if (!entry) {
        entry = { sem: new Semaphore(this.perUserMax), refs: 0 }
        this.perUser.set(userId, entry)
      }
      userSem = entry.sem
      userSlot = userSem.tryAcquire()
      if (!userSlot) {
        return { success: false, release: () => {} }
      }
      entry.refs++
    }

    const globalSlot = this.global.tryAcquire()
    if (!globalSlot) {
      if (userSlot && userSem && userId != null) {
        userSem.release()
        const entry = this.perUser.get(userId)
        if (entry) entry.refs--
      }
      return { success: false, release: () => {} }
    }

    const releasedUserId = userId
    return {
      success: true,
      release: () => {
        this.global.release()
        if (releasedUserId != null) {
          const entry = this.perUser.get(releasedUserId)
          if (entry) {
            entry.sem.release()
            entry.refs--
          }
        }
      },
    }
  }

  shutdown(): void {
    clearInterval(this.cleanupInterval)
    this.perUser.clear()
  }

  private cleanup(): void {
    for (const [key, entry] of this.perUser) {
      if (entry.refs <= 0) this.perUser.delete(key)
    }
  }
}

import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { Channel } from '@/lib/types'

const FEATURES = ['자막 기반 RAG 검색', '타임스탬프 근거 제공', '영상 내 재생 시점 이동']

interface Props {
  channels: Channel[]
  /** URL 등록 + 스캔. 성공하면 작업 환경으로 이동한다. */
  onSubmit: (url: string) => Promise<void>
  onOpenChannel: (channelId: number) => void
}

export function HomePage({ channels, onSubmit, onOpenChannel }: Props) {
  const [url, setUrl] = useState('')
  const [pending, setPending] = useState(false)
  const navigate = useNavigate()

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!url.trim()) return
    setPending(true)
    try {
      await onSubmit(url.trim())
      setUrl('')
      navigate('/workspace')
    } catch {
      // 실패 토스트는 onSubmit이 이미 띄운다. 홈에 그대로 머문다.
    } finally {
      setPending(false)
    }
  }

  return (
    // App이 고정 높이라, 홈 내용이 길면 여기서 스크롤한다.
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex min-h-full w-full max-w-2xl items-center justify-center px-4 py-16">
        <div className="w-full text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">YouTube 영상으로 대화하기</h1>
        <p className="mt-3 text-muted-foreground">
          채널 링크를 붙여 넣으면 영상을 모아 자막을 분석하고 AI에게 질문할 수 있습니다.
        </p>

        <form
          onSubmit={submit}
          className="mx-auto mt-8 flex max-w-xl items-center gap-2 rounded-xl border border-border/70 bg-card/60 p-2 shadow-lg"
        >
          <Input
            type="url"
            required
            value={url}
            placeholder="https://www.youtube.com/@channel"
            aria-label="YouTube 채널 URL"
            className="border-0 bg-transparent shadow-none focus-visible:ring-0"
            onChange={(event) => setUrl(event.target.value)}
          />
          <Button type="submit" disabled={pending || !url.trim()}>
            {pending ? '등록 중…' : '분석 시작'}
          </Button>
        </form>

        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {FEATURES.map((feature) => (
            <span
              key={feature}
              className="rounded-full border border-border/60 bg-card/40 px-3 py-1 text-xs text-muted-foreground"
            >
              {feature}
            </span>
          ))}
        </div>

        {/* 이미 등록한 채널이 있으면 바로 작업 환경으로 진입할 수 있게 한다. */}
        {channels.length > 0 && (
          <div className="mx-auto mt-12 max-w-xl rounded-xl border border-border/60 bg-card/40 p-4 text-left">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-medium">내 작업 환경</span>
              <Button variant="ghost" size="sm" onClick={() => navigate('/workspace')}>
                작업 환경 열기 <ArrowRight className="size-4" />
              </Button>
            </div>
            <ul className="flex flex-wrap gap-2">
              {channels.map((channel) => (
                <li key={channel.id}>
                  <button
                    type="button"
                    onClick={() => onOpenChannel(channel.id)}
                    className="rounded-full border border-border/60 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {channel.name || channel.url}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="mt-8 text-xs text-muted-foreground/70">
          단일 영상이 아니라 채널 URL을 넣습니다. 등록 후 영상 목록에서 분석할 영상을 고릅니다.
        </p>
        </div>
      </div>
    </div>
  )
}

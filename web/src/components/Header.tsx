import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { Workspace } from '@/lib/types'

interface Props {
  workspace: Workspace | null
  onConnect: (code: string) => Promise<void>
  onCreateNew: () => Promise<void>
}

export function Header({ workspace, onConnect, onCreateNew }: Props) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [code, setCode] = useState('')
  const [pending, setPending] = useState(false)

  const submit = async () => {
    if (!code.trim()) return
    setPending(true)
    try {
      await onConnect(code.trim())
      setDialogOpen(false)
      setCode('')
    } finally {
      setPending(false)
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-4 sm:px-6">
        {/* 로고 = 홈 버튼 */}
        <Link to="/" aria-label="홈으로" className="transition-opacity hover:opacity-80">
          <Logo />
        </Link>

        <div className="flex items-center gap-2">
          {workspace && (
            <code className="hidden rounded-md bg-muted px-2 py-1 font-mono text-xs text-muted-foreground sm:inline">
              {workspace.workspace_code}
            </code>
          )}
          <Button variant="outline" size="sm" onClick={() => setDialogOpen(true)}>
            작업공간 연결
          </Button>
          <Button variant="ghost" size="sm" onClick={onCreateNew}>
            새로
          </Button>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>기존 작업공간 연결</DialogTitle>
            <DialogDescription>
              다른 브라우저에서 만든 작업공간의 8자리 코드를 입력하면 같은 데이터에 연결됩니다.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="workspace-code">작업공간 코드</Label>
            <Input
              id="workspace-code"
              value={code}
              placeholder="예: ABCD2345"
              autoComplete="off"
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void submit()
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              취소
            </Button>
            <Button onClick={submit} disabled={pending || !code.trim()}>
              연결
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </header>
  )
}

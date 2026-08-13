import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Sidebar as SidebarShell,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { useFolders } from '@/hooks/queries/folder/use-folders'
import { useCreateFolder } from '@/hooks/mutations/folder/use-create-folder'
import { useDeleteFolder } from '@/hooks/mutations/folder/use-delete-folder'

interface Props {
  selectedFolderId: number | null
  onSelectFolder: (folderId: number | null) => void
  onError: (message: string) => void
}

/** 폴더 이름에서 아이콘 rail에 쓸 두 글자를 뽑는다. */
const folderInitials = (label: string) => label.trim().slice(0, 2).toUpperCase() || '?'

/** 폴더 전환 전용 사이드바. 폴더 안 영상 목록은 FolderVideos가 담당한다. */
export function Sidebar({ selectedFolderId, onSelectFolder, onError }: Props) {
  const { data: folders = [] } = useFolders()

  const createFolderMutation = useCreateFolder({
    onError: () => onError('폴더 생성에 실패했습니다.'),
    onSettled: (folder) => onSelectFolder(folder.id),
  })
  const deleteFolderMutation = useDeleteFolder({
    onError: () => onError('폴더 삭제에 실패했습니다.'),
  })

  const [name, setName] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  // 이름만으로 빠르게 만든다. 영상은 만든 직후 폴더 안 "영상 추가" 다이얼로그에서 넣는다.
  const addFolder = (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    createFolderMutation.mutate(name.trim(), {
      onSuccess: () => {
        setName('')
        setAddOpen(false)
      },
    })
  }

  // 삭제된 폴더가 선택 중이었으면 남은 폴더 중 하나로 옮기고, 없으면 선택을 비운다.
  const handleDelete = (event: React.MouseEvent, folderId: number) => {
    event.stopPropagation()
    if (!window.confirm('이 폴더와 안의 모든 영상을 삭제할까요? 되돌릴 수 없습니다.')) return
    setDeletingId(folderId)
    deleteFolderMutation.mutate(folderId, {
      onSuccess: () => {
        if (folderId === selectedFolderId) {
          const next = folders.find((folder) => folder.id !== folderId)
          onSelectFolder(next ? next.id : null)
        }
      },
      onSettled: () => setDeletingId(null),
    })
  }

  return (
    <SidebarShell collapsible="icon">
      <SidebarHeader className="gap-2">
        <div className="flex items-center justify-between px-1 group-data-[collapsible=icon]:justify-center">
          <span className="text-xs font-medium text-muted-foreground group-data-[collapsible=icon]:hidden">
            폴더
          </span>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-primary hover:underline group-data-[collapsible=icon]:hidden"
              >
                <Plus className="size-3.5" /> 추가
              </button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>새 폴더 만들기</DialogTitle>
                <DialogDescription>이름만 정하면 바로 만들어집니다. 영상은 만든 뒤에 추가하세요.</DialogDescription>
              </DialogHeader>
              <form onSubmit={addFolder} className="space-y-2">
                <Input
                  required
                  value={name}
                  placeholder="폴더 이름"
                  aria-label="새 폴더 이름"
                  onChange={(event) => setName(event.target.value)}
                />
                <Button
                  type="submit"
                  className="w-full"
                  disabled={createFolderMutation.isPending || !name.trim()}
                >
                  {createFolderMutation.isPending ? '생성 중…' : '생성'}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu className="px-1">
          {folders.length === 0 ? (
            <p className="px-2 py-1 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
              폴더가 없습니다. 위에서 추가하세요.
            </p>
          ) : (
            folders.map((folder) => (
              <SidebarMenuItem key={folder.id}>
                <SidebarMenuButton
                  isActive={folder.id === selectedFolderId}
                  tooltip={folder.name}
                  onClick={() => onSelectFolder(folder.id)}
                  className="gap-2"
                >
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/15 text-[10px] font-bold text-primary">
                    {folderInitials(folder.name)}
                  </span>
                  <span className="truncate">{folder.name}</span>
                </SidebarMenuButton>
                <SidebarMenuAction
                  showOnHover
                  disabled={deletingId === folder.id}
                  onClick={(event) => handleDelete(event, folder.id)}
                  aria-label={`${folder.name} 삭제`}
                >
                  <Trash2 />
                </SidebarMenuAction>
              </SidebarMenuItem>
            ))
          )}
        </SidebarMenu>
      </SidebarContent>
    </SidebarShell>
  )
}

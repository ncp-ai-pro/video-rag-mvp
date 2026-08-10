import { useState } from "react";
import { Link, Outlet } from "react-router-dom";

import Logo from "@/assets/logo.png";
import { Footer } from "@/components/Footer";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMe } from "@/hooks/queries/workspace/use-me";
import { useConnectWorkspace } from "@/hooks/mutations/workspace/use-connect-workspace";
import { useCreateWorkspace } from "@/hooks/mutations/workspace/use-create-workspace";

export default function GlobalLayout() {
  const { data: workspace } = useMe();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [code, setCode] = useState("");

  const connectWorkspaceMutation = useConnectWorkspace({
    onSuccess: () => {
      setDialogOpen(false);
      setCode("");
    },
  });
  const createWorkspaceMutation = useCreateWorkspace();

  const submitConnect = () => {
    if (!code.trim()) return;
    connectWorkspaceMutation.mutate(code.trim());
  };

  const createNewWorkspace = () => {
    const confirmed = window.confirm(
      "새 작업공간으로 전환할까요? 현재 작업공간은 코드로 다시 연결할 수 있습니다.",
    );
    if (!confirmed) return;
    createWorkspaceMutation.mutate();
  };

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="flex h-14 items-center justify-between px-4 sm:px-6">
          {/* 로고 = 홈 버튼 */}
          <Link to="/" aria-label="홈으로" className="transition-opacity hover:opacity-80">
            <img src={Logo} className="w-15 rounded-2xl" alt="VideRAG" />
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
            <Button variant="ghost" size="sm" onClick={createNewWorkspace}>
              새로
            </Button>
          </div>
        </div>
      </header>

      <Outlet />

      <Footer />

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
                if (event.key === "Enter") submitConnect();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              취소
            </Button>
            <Button
              onClick={submitConnect}
              disabled={connectWorkspaceMutation.isPending || !code.trim()}
            >
              연결
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

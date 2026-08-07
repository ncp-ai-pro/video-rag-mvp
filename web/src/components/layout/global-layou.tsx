// import { Outlet } from "react-router-dom";

// export default function GlobalLayout() {
//   return (
//     <div>
//       <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur">
//         <div className="flex h-14 items-center justify-between px-4 sm:px-6">
//           {/* 로고 = 홈 버튼 */}
//           <Link
//             to="/"
//             aria-label="홈으로"
//             className="transiation-opacity hover:opacity-80"
//           >
//             <Logo />
//           </Link>

//           <div className="flex items-center gap-2">
//             {workspace && (
//               <code className="hidden rounded-md bg-muted px-2 py-1 font-mono text-xs text-muted-foreground sm:inline">
//                 {workspace.workspace_code}
//               </code>
//             )}
//             <Button
//               variant="outline"
//               size="sm"
//               onClick={() => setDialogOpen(true)}
//             >
//               작업공간 연결
//             </Button>
//             <Button variant="ghost" size="sm" onClick={onCreateNew}>
//               새로
//             </Button>
//           </div>
//         </div>
//       </header>
//       <main>
//         <Outlet />
//       </main>
//       <footer></footer>
//     </div>
//   );
// }

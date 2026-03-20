import type { PropsWithChildren } from "react";
import Header from "./header/Header";
import Aside from "./aside/Aside";
import { useSidebar } from "../../contexts/SidebarContext";

export default function Layout({ children }: PropsWithChildren) {
    const { isExpanded } = useSidebar()
    return (
        <div className="w-full min-h-dvh grid font-family-sans transition-all"
            style={{
                gridTemplateColumns: `${isExpanded ? "300px" : "112px"} 1fr`,
                background: "radial-gradient(97% 260.66% at 86.04% 85.25%, #010101 0%, #3849B1 75.8%, #FCFDFF 100%, #EFF1FA 100%)",
            }}>
            <Aside />

            <div className="flex flex-col min-h-dvh py-7.5 px-7">
                <Header />
                <main className="flex-1 w-full flex flex-col justify-center items-center mb-30">
                    {children}
                </main>
            </div>
        </div>
    )
}
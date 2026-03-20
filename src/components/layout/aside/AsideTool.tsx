import type { PropsWithChildren } from "react"
import { useSidebar } from "../../../contexts/SidebarContext"

interface AsideToolInterface extends PropsWithChildren {
    toolIcon: string,
    onClick: () => void
}

export default function AsideTool({ toolIcon, onClick, children }: AsideToolInterface) {
    const { isExpanded } = useSidebar()

    return (
        <div onClick={onClick} className="px-10 w-full h-28 flex items-center gap-3 hover:bg-[#6b76b4] cursor-pointer transition-colors">
            <div className={`flex ${isExpanded ? "justify-start w-fit" : "justify-center w-full"}  items-center  h-full`}>
                <img src={toolIcon} alt="" />
            </div>
            {isExpanded && <p className="whitespace-nowrap text-[16px] text-left text-white">
                {children}
            </p>}
        </div>
    )
}
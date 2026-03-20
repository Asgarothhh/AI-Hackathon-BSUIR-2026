import { useSidebar } from "../../../contexts/SidebarContext";
import AsideTool from "./AsideTool";

export default function Aside() {
    const { setIsExpanded } = useSidebar()

    const handleNavigate = () => {
        setIsExpanded(false)
        window.open("http://localhost:8000/kb", '_blank');
    }

    return (
        <aside className={`
            sticky top-0 flex flex-col justify-between h-full max-h-dvh pb-4 border-r border-white/10 
            bg-[#6B76B473] backdrop-blur-md transition-all duration-300
        `}>
            <div className="flex-1 flex flex-col overflow-hidden">
                <AsideTool onClick={() => setIsExpanded(prev => !prev)} toolIcon="/icon/sidebar/burger-menu.svg" />
                <AsideTool onClick={handleNavigate} toolIcon="/icon/sidebar/table.svg">
                    База знаний
                </AsideTool>
            </div>
            <div>
                <AsideTool onClick={() => { }} toolIcon="/icon/sidebar/settings.svg" />
            </div>
        </aside>
    )
}
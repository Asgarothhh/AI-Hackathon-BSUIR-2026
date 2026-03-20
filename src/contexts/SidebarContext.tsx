import { createContext, useContext, useState, type Dispatch, type PropsWithChildren } from "react";

interface SidebarContextInterface {
    isExpanded: boolean
    setIsExpanded: Dispatch<React.SetStateAction<boolean>>
}

const SidebarContext = createContext({} as SidebarContextInterface);

export function useSidebar() {
    return useContext(SidebarContext);
}

export function SidebarProvider({ children }: PropsWithChildren) {
    const [isExpanded, setIsExpanded] = useState(false);

    return (
        <SidebarContext.Provider value={{ isExpanded, setIsExpanded }}>
            {children}
        </SidebarContext.Provider>
    );
}


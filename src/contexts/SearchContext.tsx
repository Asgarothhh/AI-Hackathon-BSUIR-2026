import { createContext, useContext, useState, type Dispatch, type PropsWithChildren } from "react";

interface SearchContextInterface {
    searchValue: string
    setSearchValue: Dispatch<React.SetStateAction<string>>
}

const SearchContext = createContext({} as SearchContextInterface);

export function useSearch() {
    return useContext(SearchContext);
}

export function SearchProvider({ children }: PropsWithChildren) {
    const [searchValue, setSearchValue] = useState("");

    return (
        <SearchContext.Provider value={{ searchValue, setSearchValue }}>
            {children}
        </SearchContext.Provider>
    );
}


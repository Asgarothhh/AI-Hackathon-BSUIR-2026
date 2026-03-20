import { useSearch } from "../../../../contexts/SearchContext";

export default function SearchBar() {
    const { searchValue, setSearchValue } = useSearch()

    return (
        <div className="mx-auto flex gap-3 items-stretch bg-[#BDC3E399] text-[#C0BFCF] w-[770px] h-[55px] rounded-[30px] px-6 border border-[#BFC5E499]">
            <div className="flex flex-col justify-center">
                <img src="/icon/search.svg" alt="search" />
            </div>
            <input type="text" value={searchValue} onChange={(e) => setSearchValue(e.target.value)} className="flex-1 outline-0" placeholder="Search" />
        </div>
    )
}

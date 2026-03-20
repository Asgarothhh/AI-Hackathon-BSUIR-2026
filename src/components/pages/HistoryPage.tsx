import SearchBar from "../blocks/history/searchBar/SearchBar";
import HistoryTable from "../blocks/history/table/HistoryTable";
import Layout from "../layout/Layout";

export default function HistoryPage() {
    return (
        <Layout>
            <div className="flex flex-col gap-16">
                <SearchBar/>
                <HistoryTable/>
            </div>
        </Layout>
    )
}
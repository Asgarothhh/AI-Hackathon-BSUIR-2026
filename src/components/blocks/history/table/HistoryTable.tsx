import { Link } from "react-router-dom";
import HistoryTableRisk from "./HistoryTableRisk";
import { useEffect, useState } from "react";
import { fetchTableData } from "../../../../api/table";
import { useSearch } from "../../../../contexts/SearchContext";

interface LinkedLawInterface {
    link: string
}

interface DataItem {
    id: string,
    before: string,
    after: string,
    risk_level: string,
    recommendation: string,
    linked_law: LinkedLawInterface
}

export default function HistoryTable() {
    const { searchValue } = useSearch()
    const [data, setData] = useState<DataItem[]>([])

    useEffect(() => {
        const fetchData = async () => {
            const resultData = await fetchTableData(searchValue)

            setData(resultData.items)
        }
        fetchData()
    }, [searchValue])

    return (
        <div className="overflow-x-auto p-4 text-white">
            <table className="w-full border-collapse text-sm text-left border border-[#C0BFCF]">
                <thead>
                    <tr className="bg-transparent border-b border-[#C0BFCF]">
                        <th className="py-6 px-4 text-[24px] font-semibold border border-[#C0BFCF]">Пункт</th>
                        <th className="py-6 pl-5 pr-30 text-[24px] font-semibold border border-[#C0BFCF]">Было</th>
                        <th className="py-6 pl-5 text-[24px] font-semibold border border-[#C0BFCF] pr-30">Стало</th>
                        <th className="py-6 pl-5 pr-5 text-[24px] font-semibold border border-[#C0BFCF] ">Риск</th>
                        <th className="py-6 pl-5 text-[24px] font-semibold border border-[#C0BFCF] px-8">
                            Рекомендации
                        </th>
                        <th className="pl-5 pr-8 text-[24px] font-semibold border border-[#C0BFCF] py-6">Ссылка</th>
                    </tr>
                </thead>
                <tbody>
                    {data.map((row, i) => (
                        <tr key={i} className="bg-transparent">
                            <td className="py-6 px-4 text-[24px] text-center align-top whitespace-pre-line border border-[#C0BFCF] font-semibold">
                                {row.id}
                            </td>
                            <td className="py-6 pl-5 pr-30 text-[16px] align-top whitespace-pre-line border border-[#C0BFCF]">
                                {row.before}
                            </td>
                            <td className="py-6 pl-5  text-[16px] align-top whitespace-pre-line border border-[#C0BFCF]">
                                {row.after}
                            </td>
                            <td className="py-6 pl-5 pr-5 text-[16px] align-top whitespace-pre-line border border-[#C0BFCF]">
                                <HistoryTableRisk riskType={row.risk_level as ("green" | "red" | "yellow")} />
                            </td>
                            <td className="py-6 pl-5  text-[16px] align-top whitespace-pre-line border border-[#C0BFCF]">
                                {row.recommendation}
                            </td>
                            <td className="py-6 pl-5 pr-8 text-[16px] align-top whitespace-pre-line border border-[#C0BFCF]">
                                <Link to={row.linked_law.link} target="_blank" className="flex h-full pt-5 justify-center items-center">
                                    <img src="/icon/link.svg" alt="Link" />
                                </Link>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
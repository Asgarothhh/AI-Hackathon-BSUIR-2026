interface HistoryTableRiskInterface {
    riskType: "green" | "yellow" | "red"
}

export default function HistoryTableRisk({ riskType }: HistoryTableRiskInterface) {
    return (
        <div className="flex flex-col items-center">
            <img className="pt-10 text-center mx-0" src={`/icon/risk/${riskType}-risk.svg`} alt={riskType} />
            <p>{riskType}</p>
        </div>
    )
}
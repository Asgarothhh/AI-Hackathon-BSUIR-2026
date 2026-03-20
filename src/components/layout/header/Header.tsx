import { Link, useLocation } from "react-router-dom";
import Container from "../../shared/container/Container";
import HeaderAccount from "./HeaderAccount";

export default function Header() {
    const location = useLocation();
    return (
        <header className="w-full h-25 grid-col-[1/3]">
            <Container>
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        {location.pathname !== "/" && <Link className="text-white text-[32px]" to={"/"}>{"<-"}</Link>}
                        <h1 className="text-[20px] text-white">
                            <Link to={"/"}>
                                Cognify Law Engine
                            </Link>
                        </h1>
                    </div>
                    <HeaderAccount />
                </div>
            </Container>
        </header>
    )
}
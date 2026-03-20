import { createBrowserRouter, createRoutesFromElements, Route, RouterProvider } from "react-router-dom";
import HomePage from "./components/pages/HomePage";
import HistoryPage from "./components/pages/HistoryPage";

const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/" element={<HomePage />} />
      <Route path="/history" element={<HistoryPage />} />
    </>
  )
)

export default function App() {
  return (
    <>
      <RouterProvider router={router} />
    </>
  )
}
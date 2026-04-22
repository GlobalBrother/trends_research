import React, { createContext, useContext, useState, ReactNode, useEffect } from "react";

interface FilterContextType {
  selectedNiche: string;
  setSelectedNiche: (niche: string) => void;
  dateRange: string;
  setDateRange: (range: string) => void;
  geo: string;
  setGeo: (geo: string) => void;
}

const FilterContext = createContext<FilterContextType | undefined>(undefined);

export function FilterProvider({ children }: { children: ReactNode }) {
  const [selectedNiche, setSelectedNiche] = useState<string>(() => {
    return localStorage.getItem("selectedNiche") || "All";
  });
  const [dateRange, setDateRange] = useState<string>("7d");
  const [geo, setGeo] = useState<string>("US");

  useEffect(() => {
    localStorage.setItem("selectedNiche", selectedNiche);
  }, [selectedNiche]);

  return (
    <FilterContext.Provider value={{
      selectedNiche,
      setSelectedNiche,
      dateRange,
      setDateRange,
      geo,
      setGeo
    }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const context = useContext(FilterContext);
  if (context === undefined) {
    throw new Error("useFilters must be used within a FilterProvider");
  }
  return context;
}

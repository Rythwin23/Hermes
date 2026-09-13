import { AgGridAngular } from 'ag-grid-angular';
import { Component } from '@angular/core';
import { AllCommunityModule, ColDef, iconSetQuartzBold, themeQuartz } from 'ag-grid-community';

@Component({
  selector: 'app-naviguer',
  imports: [AgGridAngular],
  templateUrl: './naviguer.html',
  styleUrl: './naviguer.css',
})
export class Naviguer {
  modules = [AllCommunityModule];
  myTheme = themeQuartz.withPart(iconSetQuartzBold).withParams({
    accentColor: '#176B5B',
    backgroundColor: '#FFFFFF',
    borderColor: '#DCE3DE',
    browserColorScheme: 'inherit',
    cellTextColor: '#1D2A28',
    columnBorder: false,
    fontFamily: ['Avenir Next', 'Trebuchet MS', 'sans-serif'],
    foregroundColor: '#1D2A28',
    headerBackgroundColor: '#EDF1ED',
  });

  rowData = [
    {
      departure: 'Châtelet',
      arrival: 'La Défense',
      duration: '24 min',
      changes: 0,
      line: 'Métro 1',
      path: 'Châtelet → La Défense',
    },
    {
      departure: 'Gare de Lyon',
      arrival: 'Charles de Gaulle - Étoile',
      duration: '31 min',
      changes: 1,
      line: 'RER A • Métro 6',
      path: 'Gare de Lyon → Châtelet → Charles de Gaulle - Étoile',
    },
    {
      departure: 'Saint-Lazare',
      arrival: 'Montparnasse - Bienvenüe',
      duration: '18 min',
      changes: 0,
      line: 'RER E',
      path: 'Saint-Lazare → Montparnasse - Bienvenüe',
    },
  ];

  columnDefs: ColDef[] = [
    { field: 'departure', headerName: 'Départ', minWidth: 180, sortable: true, filter: true },
    { field: 'arrival', headerName: 'Arrivée', minWidth: 180, sortable: true, filter: true },
    { field: 'duration', headerName: 'Durée', width: 120, sortable: true },
    { field: 'changes', headerName: 'Correspondances', width: 150, sortable: true },
    { field: 'line', headerName: 'Ligne', minWidth: 200, sortable: true, filter: true },
    { field: 'path', headerName: 'Parcours', minWidth: 280, sortable: true, filter: true },
  ];

  defaultColDef: ColDef = {
    resizable: true,
    flex: 1,
    minWidth: 100,
  };
}

export const myTheme = themeQuartz.withPart(iconSetQuartzBold).withParams({
  accentColor: '#1074C6',
  backgroundColor: '#FFFFFF',
  borderColor: '#002BFF3B',
  browserColorScheme: 'inherit',
  cellTextColor: '#000000',
  columnBorder: false,
  fontFamily: {
    googleFont: 'Inter',
  },
  foregroundColor: '#000000',
  headerBackgroundColor: '#0007FF4F',
});

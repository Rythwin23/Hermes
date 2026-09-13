import { Routes } from '@angular/router';
import { Home } from './home/home';
import { Naviguer } from './naviguer/naviguer';
import { Referentiels } from './referentiels/referentiels';

export const routes: Routes = [
  { path: '', component: Home },
  { path: 'naviguer', component: Naviguer },
  { path: 'referentiels', component: Referentiels },
  { path: '**', redirectTo: '' },
];

import { useEffect, useState } from 'react'
import { Bookmark, ChevronRight, LogOut, Settings2, ShoppingCart, UserRound } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, LoadingState, PageHeader, Section } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import type { Profile, Recipe } from '../lib/types'

export function ProfileScreen() {
  const { api, user, signOut, isDemo } = useAuth(); const navigate = useNavigate(); const [profile, setProfile] = useState<Profile | null>(null); const [recipes, setRecipes] = useState<Recipe[]>([])
  useEffect(() => { void Promise.all([api.profile(), api.recipes(true)]).then(([nextProfile, page]) => { setProfile(nextProfile); setRecipes(page.items) }) }, [api])
  if (!profile) return <LoadingState label="Opening your profile…" />
  return <div className="screen profile-screen">
    <PageHeader title="Your profile" subtitle="Preferences, saved plans and the meals worth repeating." />
    <div className="profile-card"><span><UserRound /></span><div><h2>{profile.display_name ?? 'FreshLoop cook'}</h2><p>{user?.email}</p><small>{isDemo ? 'Demo workspace' : 'Connected account'}</small></div></div>
    <Section title="Food preferences" action={<Link to="/onboarding"><Settings2 /> Edit</Link>}><div className="preference-summary"><div><small>Diet</small><strong>{profile.dietary_preferences.join(', ') || 'No preference'}</strong></div><div><small>Allergies</small><strong>{profile.allergies.join(', ') || 'None'}</strong></div><div><small>Cuisines</small><strong>{profile.preferred_cuisines.join(', ') || 'Surprise me'}</strong></div><div><small>Daily target</small><strong>{profile.daily_calorie_target?.toLocaleString() ?? '—'} kcal</strong></div></div></Section>
    <div className="section-heading"><h2>Saved recipes</h2><span>{recipes.length}</span></div>
    <div className="saved-list">{recipes.length ? recipes.map((recipe) => <Link to={`/recipes/${recipe.id}`} key={recipe.id}><span>🍽️</span><div><strong>{recipe.title}</strong><small>{recipe.cuisine} · {recipe.prep_minutes + recipe.cook_minutes} min</small></div><Bookmark /><ChevronRight /></Link>) : <p className="empty-inline">Saved recipes will appear here.</p>}</div>
    <div className="section-heading"><h2>Saved shopping lists</h2></div><Link className="profile-link" to="/plans/42"><ShoppingCart /><span><strong>FreshLoop week</strong><small>5 days · active list</small></span><ChevronRight /></Link>
    <Button variant="secondary" className="signout" onClick={() => void signOut().then(() => navigate('/auth'))}><LogOut /> Sign out</Button>
  </div>
}
